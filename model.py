from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) #ชื่อสินค้า
    sku = db.Column(db.String(50), unique=True, nullable=False) #รหัสSKU
    cost_price = db.Column(db.Float, nullable=False) #ราคาต้นทุนสินค้า
    category = db.Column(db.String(50)) #หมวดหมู่สินค้า เช่น Vitamin / Drug / กระดาษ  ไม่ได้มีผลอะไรกับ data
    unit = db.Column(db.String(20)) #หน่วยนับ(แบบชิ้น)
    stock = db.Column(db.Integer, default=0) #จำนวนคงเหลือสต๊อก(แบบชิ้น)
    image_filename = db.Column(db.String(200))  #ชื่อไฟล์รูปภาพ
    variants = db.relationship('ProductVariant', backref='product', cascade="all, delete-orphan")

    @property
    def serialized_variants(self):
        return [
            {
                "sku_suffix": v.sku_suffix,
                "sale_mode": v.sale_mode,
                "pack_size": v.pack_size,
                "selling_price": v.selling_price
            }
            for v in self.variants
        ]

class ProductVariant(db.Model):  ## ข้อมูล 1 SKU สินค้าอาจจะมีหลาย pack size    
    __tablename__ = 'product_variant'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    sale_mode = db.Column(db.String(50))  # รูปแบบการขาย (single, pack, box) 
    sku_suffix = db.Column(db.String(50))  # optional เช่น -P5, -P10
    pack_size = db.Column(db.Integer, nullable=False)# จำนวนหน่วยที่ขายในแต่ละรูปแบบ เช่น 5, 10  [จำนวนหน่วยย่อยต่อแพ็ค (ใช้ตอนขาย)]
    selling_price = db.Column(db.Float, nullable=True)  # ราคาขาย
    stock = db.Column(db.Integer, default=0) # จำนวนคงเหลือ
    is_for_sale = db.Column(db.Boolean, default=True) #กำหนดรูปแบบ pack_size นี้ใช้สำหรับการขาย

    def to_dict(self):
        return {
            "id": self.id,
            "pack_size": self.pack_size,
            "sku_suffix": self.sku_suffix,
            "sale_mode": self.sale_mode,
            "pack_size": self.pack_size,
            "selling_price": self.selling_price,
            "stock": self.stock,
            "is_for_sale": self.is_for_sale
        }

'''pack_size และ unit_multiplier ต่างกันเล็กน้อย
    pack_size = จำนวนหน่วยย่อยต่อแพ็ค (ใช้ตอนขาย)
    unit_multiplier = ตัวคูณจำนวนหน่วยย่อยที่ได้จากการรับเข้า (ใช้ตอนรับของเข้าคลัง)'''

class StockIn(db.Model): #ข้อมูลการรับเข้าสินค้า
    __tablename__ = 'stock_in'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    date_in = db.Column(db.DateTime, nullable=False, default=datetime.utcnow) #วันที่รับเข้า
    evidence_image = db.Column(db.String(200)) # ชื่อไฟล์ภาพหลักฐาน
    note = db.Column(db.String(200))  #บันทึกหมายเหตุ 
    product = db.relationship('Product', backref=db.backref('stockins', lazy=True))
    details = db.relationship('StockInVariant', back_populates="stock_in", cascade="all, delete-orphan")
    
    @property
    def total_units(self):
        return sum([detail.quantity * detail.unit_multiplier for detail in self.details])

class StockInVariant(db.Model): #ข้อมูลการรับเข้าสินค้าแบบมี Variant ไม่ใช่หน่วยเล็กที่สุด 1 ชิ้น เช่นเป็นลัง ก่อนมาแบ่งขาย
    __tablename__ = 'stock_in_variant'
    id = db.Column(db.Integer, primary_key=True)
    stock_in_id = db.Column(db.Integer, db.ForeignKey('stock_in.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variant.id'), nullable=True)
    variant = db.relationship('ProductVariant')
    quantity = db.Column(db.Integer, nullable=False)  # จำนวนที่รับเข้า (เช่น 3 ลัง)
    unit_multiplier = db.Column(db.Integer, nullable=False, default=1)  # เช่น 1 ลัง = 100 ชิ้น
    stock_in = db.relationship('StockIn', back_populates="details")
    sale_mode = db.Column(db.String(100), nullable=False)   # เช่น “กล่องใหญ่”
    pack_size = db.Column(db.Integer, nullable=False)

class Sale(db.Model): #ข้อมูลส่วนการขาย
    __tablename__ = 'sale' 
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    customer_name = db.Column(db.String(100))   #ชื่อลูกค้า กรณีที่ต้องการหาว่าลูกค้าประจำ / ลูกค้าใหม่ 
    date_sold = db.Column(db.DateTime, default=datetime.utcnow) #วันที่ขาย
    sale_price = db.Column(db.Float, nullable=False) # ราคาขายต่อหน่วยที่ขายไป
    channel = db.Column(db.String(50)) #ช่องทางการขาย เช่น line shopping Shopee Lazada
    commission_percent = db.Column(db.Float, default=0.0)  #ค่าธรรมเนียมการขาย
    transaction_fee = db.Column(db.Float, default=0.0) #ค่าธุรกรรมการชำระเงิน
    shop_discount = db.Column(db.Float, default=0.0) #ส่วนลดจากร้านค้า(เรา)
    platform_discount = db.Column(db.Float, default=0.0) #ส่วนลดจากช่องทางการขาย
    shipping_fee = db.Column(db.Float, default=0.0) #ค่าขนส่ง
    coin_discount = db.Column(db.Float, default=0.0) #ส่วนลดเหรียญ
    seller_receive = db.Column(db.Float, default=0.0) #ราคาที่เราได้ 
    vat_amount = db.Column(db.Float, default=0.0) #ภาษีมูลค่าเพิ่ม
    customer_total = db.Column(db.Float, default=0.0)  #ราคาที่ลูกค้าจ่าย
    shipping_province = db.Column(db.String(100)) #จังหวัดที่จัดส่ง
    product = db.relationship('Product', backref=db.backref('sales', lazy=True))
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variant.id'), nullable=False)
    variant = db.relationship("ProductVariant", backref="sales")

class SalesChannelSetting(db.Model):  ## ข้อมูลเรื่องค่าคอมมิชชั่น/การชำระเงินที่โดนหักจาก platform ต่างๆ
    __tablename__ = 'sales_channel_setting'
    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(50), unique=True, nullable=False)  # เช่น Shopee, Lazada
    commission_percent = db.Column(db.Float, default=0.0) # ค่าคอมมิชชั่นที่platform หักจากเรา เช่น 5.0
    transaction_fee = db.Column(db.Float, default=0.0)   # ธุรกรรมการชำระเงิน เช่น 10.0 (บาท)