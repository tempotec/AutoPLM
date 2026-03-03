from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed, MultipleFileField
from wtforms import StringField, TextAreaField, SelectField, SubmitField, DateField, BooleanField
from wtforms.validators import Optional


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


STATUS_CHOICES = [
    ('draft', 'Rascunho'),
    ('in_development', 'Em desenvolvimento'),
    ('approved', 'Aprovado'),
    ('in_production', 'Em producao'),
    ('completed', 'Concluido'),
]

IMPORT_CATEGORY_CHOICES = [
    ('', 'Selecione...'),
    ('roupas', 'Roupas'),
    ('decoracao', 'Decoracao'),
    ('acessorios', 'Acessorios'),
    ('bijuteria', 'Bijuteria'),
    ('bolsas', 'Bolsas'),
]


class UploadPDFForm(FlaskForm):
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier_id = SelectField('Fornecedor', coerce=int, validators=[])
    stylist = StringField('Estilista')
    is_imported = BooleanField('Documento importado')
    import_category = SelectField('Categoria do importado', choices=IMPORT_CATEGORY_CHOICES)
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


class BatchUploadForm(FlaskForm):
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
    submit = SubmitField('Iniciar Upload em Lote')


class SpecificationForm(FlaskForm):
    ref_souq = StringField('Referência (REF SOUQ)')
    description = TextAreaField('Descrição')
    collection = StringField('Coleção')
    collection_id = SelectField('Vincular à Coleção', coerce=int, validators=[])
    supplier = StringField('Fornecedor')
    corner = StringField('Corner')
    main_fabric = StringField('Matéria-prima e composição (tecido principal)')
    main_group = SelectField('Grupo', choices=GROUP_CHOICES)
    sub_group = SelectField('Subgrupo', choices=SUBGROUP_CHOICES)
    status = SelectField('Status', choices=STATUS_CHOICES)
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

    tech_sheet_delivery_date = DateField(
        'Data de Entrega Ficha T?cnica',
        format='%Y-%m-%d',
        validators=[Optional()],
    )
    pilot_delivery_date = DateField(
        'Data de Entrega Piloto',
        format='%Y-%m-%d',
        validators=[Optional()],
    )
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
