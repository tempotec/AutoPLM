from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, SubmitField, DateField


GROUP_CHOICES = [
    ('', 'Selecione...'),
    ('TECIDO PLANO', 'Tecido Plano'),
    ('MALHA', 'Malha'),
    ('TRICOT', 'Tricot'),
    ('JEANS', 'Jeans'),
]

SUBGROUP_CHOICES = [
    ('', 'Selecione...'),
    ('BLAZER', 'Blazer'),
    ('BLUSA', 'Blusa'),
    ('BRINCO', 'Brinco'),
    ('CALÇA', 'Calça'),
    ('CAMISA', 'Camisa'),
    ('CAMISA/CAMISÃO', 'Camisa/Camisão'),
    ('CAMISETA', 'Camiseta'),
    ('CARDIGÃ', 'Cardigã'),
    ('JAQUETA', 'Jaqueta'),
    ('KAFTAN', 'Kaftan'),
    ('REGATA', 'Regata'),
    ('SAIA', 'Saia'),
    ('TÚNICA', 'Túnica'),
]


class UploadPDFForm(FlaskForm):
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier_id = SelectField('Fornecedor', coerce=int, validators=[])
    stylist = StringField('Estilista')
    price_range = SelectField('Faixa de Preço',
                             choices=[
                                 ('', 'Selecione a faixa de preço...'),
                                 ('P1', 'P1'),
                                 ('P2', 'P2'),
                                 ('P3', 'P3'),
                                 ('P4', 'P4')
                             ])
    pdf_file = FileField('File',
                         validators=[
                             FileRequired(),
                             FileAllowed(['pdf', 'jpg', 'jpeg', 'png'],
                                         'Apenas PDF ou imagens (JPG, PNG)!')
                         ])
    submit = SubmitField('Upload and Process')


class SpecificationForm(FlaskForm):
    ref_souq = StringField('Referência (REF SOUQ)')
    description = TextAreaField('Descrição')
    collection = StringField('Coleção')
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier = StringField('Fornecedor')
    corner = StringField('Corner')
    main_fabric = StringField('Matéria-Prima')
    main_group = SelectField('Grupo', choices=GROUP_CHOICES)
    sub_group = SelectField('Subgrupo', choices=SUBGROUP_CHOICES)
    price_range = SelectField('Faixa de Preço',
                             choices=[
                                 ('', 'Selecione...'),
                                 ('P1', 'P1'),
                                 ('P2', 'P2'),
                                 ('P3', 'P3'),
                                 ('P4', 'P4')
                             ])

    target_price = StringField('Target Price')
    store_month = StringField('Mês Loja')
    delivery_cd_month = StringField('Mês Entrega CD')

    tech_sheet_delivery_date = DateField('Data de Entrega Ficha Técnica')
    pilot_delivery_date = DateField('Data de Entrega Piloto')
    showcase_for = StringField('Mostruário Para')

    stylists = StringField('Estilista(s)')

    composition = TextAreaField('Composição')
    pattern = StringField('Estampa/Padrão')
    colors = TextAreaField('Cores')
    tags_kit = TextAreaField('Observações e Aviamentos')

    pilot_size = StringField('Tamanho da Piloto')
    body_length = StringField('Comprimento corpo')
    sleeve_length = StringField('Comprimento da manga')
    hem_width = StringField('Largura da barra')
    shoulder_to_shoulder = StringField('Ombro a ombro')
    bust = StringField('Busto')
    waist = StringField('Cintura')
    straight_armhole = StringField('Cava reta')
    neckline_depth = StringField('Profundidade do decote')
    openings_details = TextAreaField('Aberturas ou detalhes')
    finishes = TextAreaField('Acabamentos')

    technical_drawing = TextAreaField('Desenho técnico')
    reference_photos = TextAreaField('Fotos de referência / protótipo')
    specific_details = TextAreaField('Detalhes específicos')

    submit = SubmitField('Save Specification')
