from datetime import datetime
from app.extensions import db


class Specification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    collection_id = db.Column(db.Integer, db.ForeignKey('collection.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=True)
    pdf_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ref_souq = db.Column(db.String(100))
    description = db.Column(db.Text)
    collection = db.Column(db.String(100))
    supplier = db.Column(db.String(100))
    corner = db.Column(db.String(100))
    main_fabric = db.Column(db.String(100))
    main_group = db.Column(db.String(30))
    sub_group = db.Column(db.String(30))

    target_price = db.Column(db.String(100))
    store_month = db.Column(db.String(200))
    delivery_cd_month = db.Column(db.String(200))

    tech_sheet_delivery_date = db.Column(db.Date)
    pilot_delivery_date = db.Column(db.Date)
    showcase_for = db.Column(db.String(200))

    stylists = db.Column(db.String(200))

    composition = db.Column(db.Text)
    pattern = db.Column(db.Text)
    colors = db.Column(db.Text)
    tags_kit = db.Column(db.Text)

    pilot_size = db.Column(db.String(50))
    body_length = db.Column(db.String(100))
    sleeve_length = db.Column(db.String(100))
    hem_width = db.Column(db.String(100))
    shoulder_to_shoulder = db.Column(db.String(100))
    bust = db.Column(db.String(100))
    waist = db.Column(db.String(100))
    straight_armhole = db.Column(db.String(100))
    neckline_depth = db.Column(db.String(100))
    openings_details = db.Column(db.Text)
    finishes = db.Column(db.Text)

    technical_drawing = db.Column(db.Text)
    reference_photos = db.Column(db.Text)
    specific_details = db.Column(db.Text)

    technical_drawing_url = db.Column(db.String(500))
    pdf_thumbnail = db.Column(db.String(500))

    raw_extracted_text = db.Column(db.Text)
    processing_status = db.Column(db.String(50), default='pending')

    # Campos de checkpoint para processamento em etapas
    # Etapas: 0=pending, 1=thumbnail, 2=extract_image, 3=extract_text, 4=openai_parse, 5=supplier_link, 6=completed
    processing_stage = db.Column(db.Integer, default=0)
    last_error = db.Column(db.Text)
    error_stage = db.Column(db.Integer)
    retry_count = db.Column(db.Integer, default=0)
    batch_id = db.Column(db.String(50))  # Para agrupar uploads em lote
    extracted_images_json = db.Column(db.Text)  # Cache de imagens extraídas do PDF

    status = db.Column(db.String(50), default='draft')
    price_range = db.Column(db.String(10))

    collection_obj = db.relationship('Collection', backref='specifications', lazy=True)
    supplier_obj = db.relationship('Supplier', backref='specifications', lazy=True)
