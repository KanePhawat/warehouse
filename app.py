from flask import Flask, render_template, request, redirect, url_for,render_template, flash
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask import jsonify, request
from werkzeug.utils import secure_filename
import os , csv
from io import TextIOWrapper
import math
from sqlalchemy import and_
import json
from sqlalchemy.orm import joinedload
from model import db, Product, ProductVariant, StockIn, StockInVariant, Sale, SalesChannelSetting

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

basedir = os.path.abspath(os.path.dirname(__file__))
DELETE_PASSWORD = "1234"  # เปลี่ยนรหัสผ่านตรงนี้ได้

UPLOAD_FOLDER = os.path.join(basedir, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # สร้างอัตโนมัติถ้ายังไม่มี
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# ต่อด้วยการตั้งค่าอื่นๆ เช่น database config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data', 'warehouse.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default
    
def serialize_variant(variant):
    return {
        "sku_suffix": variant.sku_suffix or "",
        "sale_mode": variant.sale_mode or "",
        "pack_size": variant.pack_size or 0,
        "selling_price": float(variant.selling_price or 0),
        "stock": variant.stock or 0,
    }

def serialize_product(product):
    return {
        "id": product.id,
        "name": product.name,
        "sku": product.sku,
        "category": product.category,
        "unit": product.unit,
        "cost_price": float(product.cost_price or 0),
        "selling_price": float(product.selling_price or 0),
        "image_filename": product.image_filename,
        "variants": [serialize_variant(v) for v in product.variants],
    }

## A-1. ฟังกชั่นเพิ่มสินค้าใหม่-----------------------------------------------------------
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        mode = request.form.get('mode', 'form')
        
        if mode == 'csv':
            file = request.files.get('csv_file')
            if not file:
                flash('❌ กรุณาเลือกไฟล์ CSV', 'error')
                return redirect(request.url)

            stream = TextIOWrapper(file.stream, encoding='utf-8-sig')
            reader = csv.DictReader(stream)
            if reader.fieldnames and reader.fieldnames[0].startswith('\ufeff'):
                reader.fieldnames[0] = reader.fieldnames[0].replace('\ufeff', '')

            updated_count = 0
            added_count = 0
             
            for row in reader:
                sku = row['sku'].strip()
                cost_price = safe_float(row.get('cost_price'))
                selling_price = safe_float(row.get('selling_price'))
                
                existing = Product.query.filter_by(sku=sku).first()

                if existing:
                    updated = False
                    if existing.name != row['name']:
                        existing.name = row['name']
                        updated = True
                    if existing.cost_price != cost_price:
                        existing.cost_price = cost_price
                        updated = True
                    if existing.selling_price != selling_price and selling_price > 0:
                        existing.selling_price = selling_price
                        updated = True
                    if existing.category != row.get('category', ''):
                        existing.category = row.get('category', '')
                        updated = True
                    if existing.unit != row.get('unit', ''):
                        existing.unit = row.get('unit', '')
                        updated = True
                    if existing.image_filename != row.get('image_filename'):
                        existing.image_filename = row.get('image_filename') or None
                        updated = True

                    if updated:
                        updated_count += 1
                        print(f"✏️ อัปเดตสินค้า SKU: {sku}")
                else:
                    product = Product(
                        name=row['name'],
                        sku=sku,
                        cost_price=cost_price,
                        category=row.get('category', ''),
                        unit=row.get('unit', ''),
                        stock=int(row.get('stock', 0)),
                        image_filename=row.get('image_filename') or None,
                        selling_price=selling_price if selling_price > 0 else 0.0
                    )
                    db.session.add(product)
                    added_count += 1
                    print(f"➕ เพิ่มสินค้าใหม่ SKU: {sku}")

            try:
                db.session.commit()
                flash(f'✅ นำเข้า CSV สำเร็จ: เพิ่ม {added_count} รายการ, อัปเดต {updated_count} รายการ', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'❌ เกิดข้อผิดพลาด: {str(e)}', 'error')

            return redirect(url_for('add_product'))

        else:
            # เพิ่มสินค้าจากฟอร์มปกติ
            name = request.form['name']
            sku = request.form['sku'].strip()
            if not sku:
                flash("❌ กรุณาระบุ SKU", "error")
                return redirect(request.url)
            cost_price_raw = request.form.get('cost_price')
            cost_price = float(cost_price_raw) if cost_price_raw not in (None, '', 'null') else 0.0
            category = request.form['category']
            unit = request.form['unit']
            #sale_mode = request.form.get('sale_mode', 'single')
            #pack_size = int(request.form.get('pack_size') or 1)
            file = request.files['image']
            filename = None

            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            existing = Product.query.filter_by(sku=sku).first()
            if existing:
                flash(f'❌ SKU "{sku}" มีอยู่แล้ว กรุณาใช้รหัสอื่นหรืออัปโหลดผ่าน CSV', 'error')
                return redirect(request.url)

            product = Product(
                name=name,
                sku=sku,
                cost_price=cost_price,
                category=category,
                unit=unit,
                stock=0,
                image_filename=filename,
                selling_price=None
            )
            db.session.add(product)
            db.session.flush()  # ให้ได้ product.id ก่อน commit

            # ✅ เพิ่ม Variants
            variant_json = request.form.get("variant_data")
            try:
                variants = json.loads(variant_json)
                valid_variants = [v for v in variants if safe_int(v.get("pack_size")) > 0 and safe_float(v.get("selling_price")) > 0]
                
                if not valid_variants:
                    flash("❌ ต้องเพิ่มรูปแบบการขายอย่างน้อย 1 แบบ", "error")
                    return redirect(request.url)
                
                for v in valid_variants:
                    pack_size = safe_int(v.get("pack_size"))
                    selling_price = safe_float(v.get("selling_price"))
                    sale_mode = v.get("sale_mode", "ยกแพ็ค")
                    sku_suffix = v.get("sku_suffix", "")

                    if pack_size > 0 and selling_price > 0:
                        variant = ProductVariant(
                            product_id=product.id,
                            pack_size=pack_size,
                            selling_price=selling_price,
                            sale_mode=sale_mode,
                            sku_suffix=sku_suffix,
                            stock=0  # เริ่มต้นที่ 0
                        )
                        db.session.add(variant)  # ✅ เพิ่มตรงนี้
                        
                        if sale_mode == "single":
                            product.selling_price = selling_price  #✅ ใช้เฉพาะเมื่อมี single จริง
                            

            except Exception as e:
                print("❌ ผิดพลาดในการแปลง variant_data:", e)
                flash("❌ ไม่สามารถเพิ่มรูปแบบการขายเพิ่มเติมได้", "error")

            db.session.commit()
            flash('✅ เพิ่มสินค้าสำเร็จ', 'success')
            return redirect(url_for('add_product'))
    return render_template('add_product.html')

## A-2. ฟังกชั่นแก้ไขสินค้า เพิ่มเติม Product Variant--เช่นขายแบบแพ็ค-------------------------
@app.route('/edit_product/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    # อัปเดตข้อมูลพื้นฐาน
    product.name = request.form['name']
    product.sku = request.form['sku']
    product.category = request.form['category']
    product.unit = request.form['unit']
    product.cost_price = safe_float(request.form.get('cost_price'))


    # ตรวจว่ามี variants ไหม
    variant_count = request.form.get("variant_count", type=int)

    if variant_count:
        # ถ้ามี variants → เคลียร์ของเก่าก่อน แล้วเพิ่มใหม่ทั้งหมด
        ProductVariant.query.filter_by(product_id=product.id).delete()
        product.selling_price = 0

        for i in range(variant_count):
            suffix = request.form.get(f'variant_sku_suffix_{i}')
            sale_mode = request.form.get(f'variant_sale_mode_{i}')
            pack_size = safe_int(request.form.get(f'variant_pack_size_{i}'))
            selling_price = safe_float(request.form.get(f'variant_selling_price_{i}'))
            stock = safe_int(request.form.get(f'variant_stock_{i}'))
            
            # ✅ ข้ามถ้าไม่สมบูรณ์
            if pack_size <= 0 or selling_price <= 0:
                continue
            
            variant = ProductVariant(
                product_id=product.id,
                sku_suffix=suffix,
                sale_mode=sale_mode,
                pack_size=pack_size,
                selling_price=selling_price,
                stock=stock or 0
            )
            db.session.add(variant)
            
            if sale_mode == "single":
                product.selling_price = selling_price
    else:
        product.selling_price = safe_float(request.form.get("selling_price"))
        if product.selling_price <= 0:
            flash("❌ ต้องระบุราคาขาย", "error")
            return redirect(url_for('index'))

    if 'image' in request.files:
        file = request.files['image']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            product.image_filename = filename

    db.session.commit()
    flash("✅ แก้ไขสินค้าสำเร็จ", "success")
    return redirect(url_for('index'))

## A-3. ฟังกชั่นลบข้อมูลสินค้า-----------------------------------------------------------
@app.route('/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    data = request.get_json()
    
    if not data or data.get('password') != DELETE_PASSWORD:
        return jsonify({'success': False, 'message': '❌ รหัสผ่านไม่ถูกต้อง'}), 403

    product = Product.query.get_or_404(product_id)

    # 🔥 ลบ variants ที่เกี่ยวข้องก่อน (ป้องกัน constraint error)
    for variant in product.variants:
        db.session.delete(variant)

    # ลบรูป
    if product.image_filename:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], product.image_filename)
        if os.path.exists(image_path):
            os.remove(image_path)

    db.session.delete(product)
    db.session.commit()

    return jsonify({'success': True})

## B-1 ฟังกชั่นรับเข้าสินค้า-----------------------------------------------------------
@app.route('/stock_in/<int:product_id>', methods=['GET', 'POST'])
def stock_in(product_id):
    product = Product.query.get_or_404(product_id)
    variants_json = [v.to_dict() for v in product.variants if v.is_for_sale]
    
    from sqlalchemy.orm import joinedload
    history = StockIn.query \
        .filter_by(product_id=product.id) \
        .order_by(StockIn.date_in.desc()) \
        .options(joinedload(StockIn.details)) \
        .all()
    
    if request.method == 'POST':
        # ⏰ วันที่รับเข้า
        date_in_str = request.form.get('date_in')
        date_in = datetime.strptime(date_in_str, '%Y-%m-%d')
        note = request.form.get('note')

        # 📸 แนบรูปหลักฐาน
        file = request.files.get('evidence')
        filename = None
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            filepath = os.path.join('static/uploads', filename)
            file.save(filepath)

        # ➕ สร้าง StockIn หลัก
        stock_in_record = StockIn(
            product_id=product.id,
            date_in=date_in,
            evidence_image=filename,
            note=note
        )
        db.session.add(stock_in_record)
        db.session.flush()

        # ✅ 1. รับเข้าจาก dropdown เลือกรูปแบบการขาย
        variant_ids = request.form.getlist('variant_id[]')
        variant_qtys = request.form.getlist('variant_qty[]')

        for var_id, qty_str in zip(variant_ids, variant_qtys):
            try:
                variant = ProductVariant.query.get(int(var_id))
                qty = int(qty_str)
                if variant and qty > 0:
                    siv = StockInVariant(
                        stock_in_id=stock_in_record.id,
                        variant_id=variant.id,
                        quantity=qty,
                        unit_multiplier=variant.pack_size,
                        sale_mode=variant.sale_mode,
                        pack_size=variant.pack_size
                    )
                    db.session.add(siv)

                    # อัปเดต stock
                    variant.stock += qty
                    product.stock += qty * variant.pack_size
            except Exception as e:
                print(f"❌ Error in dropdown variant: {e}")
                continue

        # ✅ 2. รับเข้าแบบ Custom (ไม่ได้มีในรายการขาย)
        custom_variant_name = request.form.getlist('custom_variant_name[]')
        custom_variant_pack_size = request.form.getlist('custom_variant_pack_size[]')
        custom_variant_qty = request.form.getlist('custom_variant_qty[]')

        for mode, size, qty in zip(custom_variant_name, custom_variant_pack_size, custom_variant_qty):
            try:
                qty = int(qty)
                pack_size = int(size)
            except ValueError:
                continue

            if qty > 0 and pack_size > 0:
                # ✅ ไม่สร้าง ProductVariant อีกแล้ว
                custom_variant = ProductVariant(
                product_id=product.id,
                sale_mode=mode.strip(),
                pack_size=pack_size,
                is_for_sale=False,
                stock=qty
                )
                db.session.add(custom_variant)
                db.session.flush()
                
                # ➕ เพิ่ม StockInVariant
                siv = StockInVariant(
                    stock_in_id=stock_in_record.id,
                    variant_id=custom_variant.id,
                    quantity=qty,
                    unit_multiplier=pack_size,
                    sale_mode=mode.strip(),
                    pack_size=pack_size
                )
                db.session.add(siv)
                db.session.flush()

                # ✅ เพิ่มเข้ายอดรวม stock
                product.stock += qty * pack_size

        db.session.commit()
        flash("✅ บันทึกรับเข้าสำเร็จ", "success")
        return redirect(url_for('stock_in', product_id=product.id))

    # GET method
    history = sorted(product.stockins, key=lambda r: r.date_in)
    return render_template(
        'stock_in.html',
        product=product,
        history=history,
        current_date=datetime.today().date(),
        variants_json=variants_json
    )

## B-2 ฟังชั่นก์แก้ไขรายการรับเข้าสินค้า-----------------------------------------------------------
@app.route('/stock_in/edit/<int:record_id>', methods=['POST'])
def edit_stock_in(record_id):
    record = StockIn.query.get_or_404(record_id)
    old_qty = record.quantity

    new_date = request.form.get('date_in')
    new_qty = int(request.form.get('quantity'))
    note = request.form.get('note')  # 📝 เพิ่ม

    if not new_date or new_qty <= 0:
        return jsonify({'success': False, 'message': 'ข้อมูลไม่ถูกต้อง'}), 400

    # ปรับสต๊อกสินค้า
    product = Product.query.get_or_404(record.product_id)
    product.stock += new_qty - old_qty

    record.date_in = datetime.strptime(new_date, '%Y-%m-%d')
    record.quantity = new_qty
    record.note = note

    # รูปใหม่
    if 'evidence' in request.files:
        file = request.files['evidence']
        if file and file.filename:
            # ลบไฟล์เก่า
            if record.evidence_image:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], record.evidence_image)
                if os.path.exists(old_path):
                    os.remove(old_path)

            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            record.evidence_image = filename

    db.session.commit()
    return jsonify({'success': True})

## B-3 ฟังชั่นก์ลบรายการรับเข้าสินค้า-----------------------------------------------------------
@app.route('/stock_in/delete/<int:record_id>', methods=['POST'])
def delete_stock_in(record_id):
    data = request.get_json()
    password = data.get("password")

    if password != DELETE_PASSWORD: 
        return jsonify({"success": False, "message": "รหัสผ่านไม่ถูกต้อง"})
    
    record = StockIn.query.get_or_404(record_id)

    # ✅ ลด stock ย้อนกลับก่อนลบ
    for detail in record.details:
        if detail.variant:
            detail.variant.stock -= detail.quantity
        if record.product:
            record.product.stock -= detail.quantity * detail.unit_multiplier

    db.session.delete(record)
    db.session.commit()
    return jsonify({"success": True})

# หน้าแสดงสินค้าทั้งหมด
@app.route('/')
def index():
    products = Product.query.options(db.joinedload(Product.variants)).all()
    return render_template("index.html", products=products)

## C-1 ฟังก์ชั่นกรอกขายสินค้า-----------------------------------------------------------
@app.route('/sell/<int:product_id>', methods=['GET', 'POST'])
def sell_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        date_sold = datetime.strptime(request.form['date_sold'], '%Y-%m-%d')  # ✅ แปลงเป็น datetime
        customer_name = request.form['customer_name']
        quantity = int(request.form['quantity'])
        price = float(request.form['price'])
        channel = request.form['channel']
        shop_discount = float(request.form.get('shop_discount') or 0)
        platform_discount = float(request.form.get('platform_discount') or 0)
        shipping_fee = float(request.form.get('shipping_fee') or 0)
        coin_discount = float(request.form.get('coin_discount') or 0)
        shipping_province = request.form.get('shipping_province')
                
        # ✅ ดึงค่าคอมฯ กับค่าธุรกรรม
        channel_setting = SalesChannelSetting.query.filter_by(channel=channel).first()
        commission = channel_setting.commission_percent if channel_setting else 0
        transaction_fee = channel_setting.transaction_fee if channel_setting else 0
        
        
        ## การคำนวณค่าต่างๆ
        # 1. ราคาขายสุทธิ
        total_price = quantity * price
        # 2. ยอดที่ลูกค้าต้องชำระ
        customer_total = total_price - shop_discount  -platform_discount - coin_discount + shipping_fee
        # 3. ค่าธุรกรรมการชำระเงิน
        transaction_fee = round((customer_total + platform_discount + coin_discount) * (transaction_fee / 100))
        # 4. ยอดที่ผู้ขายได้รับ
        commission_value = math.floor(total_price * (commission / 100))
        seller_receive = total_price - commission_value - transaction_fee - shop_discount
        # 5. VAT
        vat = (commission_value + transaction_fee) * 7 / 107

        if quantity > product.stock:
            return "❌ จำนวนเกินจากสินค้าคงเหลือ", 400

        # หักสต๊อก
        product.stock -= quantity

        # บันทึกการขาย
        new_sale = Sale(
            product_id=product.id,
            date_sold=date_sold,
            customer_name=customer_name,
            quantity=quantity,
            sale_price=price,
            channel=channel,
            commission_percent=commission,
            transaction_fee=transaction_fee,
            shop_discount=shop_discount,
            platform_discount=platform_discount,
            shipping_fee=shipping_fee,
            coin_discount=coin_discount,
            customer_total=customer_total,
            seller_receive=seller_receive,
            vat_amount=vat,
            shipping_province=shipping_province,
        )
        db.session.add(new_sale)
        db.session.commit()

        return redirect(url_for('sell_product', product_id=product.id))

    # ✅ สำหรับหน้า GET (แสดงแบบฟอร์ม)
    filters = [Sale.product_id == product.id]

    # ✅ ช่วงวันที่
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            filters.append(Sale.date_sold >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            filters.append(Sale.date_sold <= end_dt)
        except ValueError:
            pass

    # ✅ ช่องทาง
    channel = request.args.get('channel')
    if channel:
        filters.append(Sale.channel == channel)

    # กรองและแสดง
    sales_history = Sale.query.filter(and_(*filters)).order_by(Sale.date_sold.desc()).all()
    channels = SalesChannelSetting.query.all()  # ✅ เพิ่มเพื่อใช้ใน dropdown
    
    return render_template(
        'sell_product.html',
        product=product,
        sales_history=sales_history,
        current_date=date.today().isoformat(),
        channels=channels,  # ✅ ส่งค่าไป dropdown
    )
    
## C-2 ฟังก์ชั่นแก้ไขรายการขายสินค้า-----------------------------------------------------------
@app.route('/sale/edit/<int:sale_id>', methods=['POST'])
def edit_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    product = Product.query.get_or_404(sale.product_id)
    
    try:
        old_qty = sale.quantity

        # รับค่าจาก form
        new_date = request.form.get('date_sold')
        new_qty = int(request.form.get('quantity'))
        new_price = float(request.form.get('price'))
        new_customer = request.form.get('customer_name')
        new_channel = request.form.get('channel')
        new_shop_discount = float(request.form.get('shop_discount') or 0)
        new_platform_discount = float(request.form.get('platform_discount') or 0)
        shipping_fee = float(request.form.get('shipping_fee') or 0)
        coin_discount = float(request.form.get('coin_discount') or 0)
        shipping_province = request.form.get('shipping_province')

        # ดึงค่าธรรมเนียมจากช่องทางการขายใหม่
        channel_setting = SalesChannelSetting.query.filter_by(channel=new_channel).first()
        commission = channel_setting.commission_percent if channel_setting else 0
        transaction_fee_percent = channel_setting.transaction_fee if channel_setting else 0

        # คำนวณยอดใหม่
        subtotal = new_qty * new_price
        customer_total = subtotal - new_shop_discount - new_platform_discount - coin_discount + shipping_fee
        transaction_fee = round((customer_total + new_platform_discount + coin_discount) * (transaction_fee_percent / 100))
        commission_value = math.floor(subtotal * (commission / 100))
        seller_receive = subtotal - commission_value - transaction_fee - new_shop_discount
        vat = (commission_value + transaction_fee) * 7 / 107

        # ตรวจสอบสต๊อก
        if new_qty > (product.stock + old_qty):
            return jsonify({'success': False, 'message': '❌ จำนวนเกินจากสินค้าคงเหลือ'}), 400

        # ปรับสต๊อก
        product.stock += old_qty - new_qty

        # อัปเดต sale record
        sale.date_sold = datetime.strptime(new_date, '%Y-%m-%d')
        sale.quantity = new_qty
        sale.sale_price = new_price
        sale.customer_name = new_customer
        sale.channel = new_channel
        sale.shop_discount = new_shop_discount
        sale.platform_discount = new_platform_discount
        sale.coin_discount = coin_discount
        sale.shipping_fee = shipping_fee
        sale.shipping_province = shipping_province

        # อัปเดตการคำนวณใหม่
        sale.commission_percent = commission
        sale.transaction_fee = transaction_fee
        sale.customer_total = customer_total
        sale.seller_receive = seller_receive
        sale.vat_amount = vat

        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

## C-3 ฟังก์ชั่นลบรายการขายสินค้า-----------------------------------------------------------
@app.route('/sale/delete/<int:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    data = request.get_json()
    if not data or data.get('password') != DELETE_PASSWORD:
        return jsonify({'success': False, 'message': '❌ รหัสผ่านไม่ถูกต้อง'}), 403

    sale = Sale.query.get_or_404(sale_id)

    # คืน stock กลับ
    product = Product.query.get(sale.product_id)
    if product:
        product.stock += sale.quantity

    db.session.delete(sale)
    db.session.commit()
    return jsonify({'success': True})

def setup_default_sales_channels():
    default_channels = [
        {'channel': 'Shopee', 'commission_percent': 8.56, 'transaction_fee': 3.21},
        {'channel': 'Lazada', 'commission_percent': 6.0, 'transaction_fee': 12.0},
        {'channel': 'Facebook', 'commission_percent': 0.0, 'transaction_fee': 0.0}
    ]
    for ch in default_channels:
        if not SalesChannelSetting.query.filter_by(channel=ch['channel']).first():
            db.session.add(SalesChannelSetting(**ch))
    db.session.commit()

## สำหรับตั้งค่าคอมมิชชั่นช่องทางการขาย
@app.route('/manage_channels', methods=['GET', 'POST'])
def manage_channels():
    if request.method == 'POST':
        password = request.form.get('password')
        if password != DELETE_PASSWORD:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message='❌ รหัสผ่านไม่ถูกต้อง')
            flash('❌ รหัสผ่านไม่ถูกต้อง', 'error')
            return redirect(url_for('manage_channels'))
        
        channel = request.form['channel']
        commission = float(request.form['commission_percent'])
        fee = float(request.form['transaction_fee'])

        existing = SalesChannelSetting.query.filter_by(channel=channel).first()
        if existing:
            existing.commission_percent = commission
            existing.transaction_fee = fee
        else:
            db.session.add(SalesChannelSetting(
                channel=channel,
                commission_percent=commission,
                transaction_fee=fee
            ))
        db.session.commit()
        
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(success=True, message="✅ บันทึกสำเร็จ")

        flash("✅ บันทึกสำเร็จ", "success")
        return redirect(url_for('manage_channels'))

    channels = SalesChannelSetting.query.all()
    return render_template("manage_channels.html", channels=channels)

## สำหรับลบช่องทางการขายต่าง
@app.route('/delete_channel', methods=['POST'])
def delete_channels():
    data = request.get_json()
    channel = data.get('channel').strip()
    password = data.get('password')

    if password != DELETE_PASSWORD:
        return jsonify(success=False, message="รหัสผ่านไม่ถูกต้อง")

    ch = SalesChannelSetting.query.filter_by(channel=channel).first()

    if not ch:
        return jsonify(success=False, message="❌ ไม่พบช่องทางที่ชื่อ: " + channel)

    db.session.delete(ch)
    db.session.commit()
    return jsonify(success=True, message="✅ ลบสำเร็จ")

## แสดงรายละเอียดการคำนวณในสินค้าขาย
@app.route("/sale/report/<int:sale_id>")
def sale_report_detail(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    subtotal = (sale.quantity or 0) * (sale.sale_price or 0)
    fee_percent = (sale.commission_percent or 0) + 7.49  # รวมค่าธรรมเนียม + VAT
    fee_amount = subtotal * fee_percent / 100

    customer_total = subtotal + (sale.shipping_fee or 0) - (sale.shop_discount or 0) - (sale.platform_discount or 0) - (sale.coin_discount or 0)
    seller_receive = subtotal - fee_amount

    product_name = sale.product.name if sale.product else "ไม่พบข้อมูลสินค้า"
    product_sku = sale.product.sku if hasattr(sale.product, 'sku') else "-"
    
    channel_setting = SalesChannelSetting.query.filter_by(channel=sale.channel).first()
    commission_percent = channel_setting.commission_percent if channel_setting else 0
    transaction_fee_percent = channel_setting.transaction_fee if channel_setting else 0

    return render_template(
        "sale_report_detail.html",
        sale=sale,
        subtotal=subtotal,
        fee_amount=fee_amount,
        customer_total=customer_total,
        seller_receive=seller_receive,
        product_name=product_name,
        product_sku=product_sku,
        commission_percent=commission_percent,
        transaction_fee_percent=transaction_fee_percent
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # สร้างตารางฐานข้อมูลถ้ายังไม่มี
        setup_default_sales_channels()  # 👈 เรียกตรงนี้
    app.run(debug=True)
