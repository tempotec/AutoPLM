import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, TextAreaField, PasswordField, SelectField, SubmitField, DateField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import PyPDF2
from functools import wraps
import base64
from PIL import Image
import io

# Import OpenAI functionality
from openai import OpenAI

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SESSION_SECRET')
if not app.config['SECRET_KEY']:
    raise RuntimeError("SESSION_SECRET environment variable is required")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # Verifica conexões antes de usar
    'pool_recycle': 3600,  # Reconecta a cada hora
    'pool_timeout': 30,  # Timeout de 30 segundos para conexões
}
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

# Make CSRF token available in templates
from flask_wtf.csrf import generate_csrf


@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)


# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship with specifications
    specifications = db.relationship('Specification',
                                     backref='user',
                                     lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Specification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pdf_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 1. Identificação da Peça
    ref_souq = db.Column(db.String(100))
    description = db.Column(db.Text)
    collection = db.Column(db.String(100))
    supplier = db.Column(db.String(100))
    corner = db.Column(db.String(100))

    # 2. Informações Comerciais
    target_price = db.Column(db.String(100))
    store_month = db.Column(db.String(200))
    delivery_cd_month = db.Column(db.String(200))

    # 3. Prazos e Entregas
    tech_sheet_delivery_date = db.Column(db.Date)
    pilot_delivery_date = db.Column(db.Date)
    showcase_for = db.Column(db.String(200))

    # 4. Equipe Envolvida
    stylists = db.Column(db.String(200))

    # 5. Matéria-Prima e Aviamentos
    composition = db.Column(db.Text)
    colors = db.Column(db.Text)
    tags_kit = db.Column(db.Text)

    # 6. Especificações Técnicas da Modelagem
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

    # 7. Design e Estilo
    technical_drawing = db.Column(db.Text)
    reference_photos = db.Column(db.Text)
    specific_details = db.Column(db.Text)

    # Generated technical drawing
    technical_drawing_url = db.Column(db.String(500))

    # Raw extracted text and status
    raw_extracted_text = db.Column(db.Text)
    processing_status = db.Column(
        db.String(50),
        default='pending')  # pending, processing, completed, error


# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class CreateUserForm(FlaskForm):
    username = StringField('Username',
                           validators=[DataRequired(),
                                       Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password',
                             validators=[DataRequired(),
                                         Length(min=6)])
    is_admin = SelectField('Role',
                           choices=[('0', 'User'), ('1', 'Admin')],
                           coerce=int)
    submit = SubmitField('Create User')


class UploadPDFForm(FlaskForm):
    pdf_file = FileField(
        'PDF File',
        validators=[FileRequired(),
                    FileAllowed(['pdf'], 'PDF files only!')])
    submit = SubmitField('Upload and Process')


class SpecificationForm(FlaskForm):
    # 1. Identificação da Peça
    ref_souq = StringField('Referência (REF SOUQ)')
    description = TextAreaField('Descrição')
    collection = StringField('Coleção')
    supplier = StringField('Fornecedor')
    corner = StringField('Corner')

    # 2. Informações Comerciais
    target_price = StringField('Target Price')
    store_month = StringField('Mês Loja')
    delivery_cd_month = StringField('Mês Entrega CD')

    # 3. Prazos e Entregas
    tech_sheet_delivery_date = DateField('Data de Entrega Ficha Técnica')
    pilot_delivery_date = DateField('Data de Entrega Piloto')
    showcase_for = StringField('Mostruário Para')

    # 4. Equipe Envolvida
    stylists = StringField('Estilista(s)')

    # 5. Matéria-Prima e Aviamentos
    composition = TextAreaField('Composição')
    colors = TextAreaField('Cores')
    tags_kit = TextAreaField('Kit Etiquetas + Tag + Pendurador Cabide')

    # 6. Especificações Técnicas da Modelagem
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

    # 7. Design e Estilo
    technical_drawing = TextAreaField('Desenho técnico')
    reference_photos = TextAreaField('Fotos de referência / protótipo')
    specific_details = TextAreaField('Detalhes específicos')

    submit = SubmitField('Save Specification')


# Helper functions
def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Admin access required.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
    return text


def extract_images_from_pdf(pdf_path):
    """Extract images from PDF and return as base64 encoded strings"""
    images_base64 = []
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(pdf_reader.pages):
                # Try to extract images from page
                if '/XObject' in page['/Resources']:
                    xObject = page['/Resources']['/XObject'].get_object()
                    for obj in xObject:
                        if xObject[obj]['/Subtype'] == '/Image':
                            try:
                                # Get image data
                                size = (xObject[obj]['/Width'], xObject[obj]['/Height'])
                                data = xObject[obj].get_data()
                                
                                # Convert to PIL Image
                                if xObject[obj]['/ColorSpace'] == '/DeviceRGB':
                                    img = Image.frombytes('RGB', size, data)
                                elif xObject[obj]['/ColorSpace'] == '/DeviceGray':
                                    img = Image.frombytes('L', size, data)
                                else:
                                    continue
                                
                                # Convert to base64
                                buffered = io.BytesIO()
                                img.save(buffered, format="PNG")
                                img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                                images_base64.append(img_base64)
                            except Exception as e:
                                print(f"Error extracting image from page {page_num}: {e}")
                                continue
    except Exception as e:
        print(f"Error processing PDF for images: {e}")
    
    return images_base64


def analyze_images_with_gpt4_vision(images_base64):
    """Use GPT-4 Vision to analyze garment images and describe technical details"""
    if not images_base64:
        print("No images provided for GPT-4 Vision analysis")
        return None
    
    if not openai_client:
        print("OpenAI client not initialized")
        return None
    
    try:
        print(f"Analyzing {len(images_base64)} images with GPT-4 Vision...")
        
        # Build messages with images
        content = [{
            "type": "text",
            "text": """Analise esta(s) imagem(ns) de peça de vestuário e descreva DETALHADAMENTE os seguintes aspectos técnicos:

1. TIPO DE PEÇA: Qual é a peça (camisa, blusa, vestido, calça, etc.)
2. SHAPE/SILHUETA: Descrição da forma geral (ajustada, solta, reta, evasê, etc.)
3. GOLA: Tipo e formato exato (redonda, V, careca, polo, colarinho, etc.)
4. MANGAS: Comprimento e estilo (curta, longa, 3/4, raglan, bufante, etc.)
5. COMPRIMENTO: Da peça em relação ao corpo (cropped, na cintura, no quadril, midi, longo)
6. RECORTES E COSTURAS: Onde ficam as linhas de costura visíveis
7. FECHAMENTOS: Tipo e localização (botões, zíper, amarração, etc.)
8. ACABAMENTOS: Detalhes como bainhas, punhos, vivos, pespontos
9. BOLSOS: Se tem, onde ficam e que tipo são
10. OUTROS DETALHES: Pregas, franzidos, pences, aplicações, etc.

Seja PRECISO e OBJETIVO. Descreva apenas o que REALMENTE aparece na imagem, sem inventar detalhes."""
        }]
        
        # Add all images
        for img_b64 in images_base64[:3]:  # Limit to first 3 images to save tokens
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high"
                }
            })
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # GPT-4o with vision
            messages=[{
                "role": "user",
                "content": content
            }],
            max_tokens=1000
        )
        
        description = response.choices[0].message.content
        print(f"GPT-4 Vision analysis successful: {description[:100]}...")
        return description
        
    except Exception as e:
        print(f"Error analyzing images with GPT-4 Vision: {e}")
        import traceback
        traceback.print_exc()
        return None


def build_technical_drawing_prompt(spec, visual_description=None):
    """Build professional technical flat sketch prompt with measurements and POMs for GPT-Image-1"""
    
    # Determine garment type from description
    garment_type = spec.description or "peça de roupa"
    
    # Build size information
    size_base = spec.pilot_size or "M/P"
    
    # Build material and composition info
    material_info = spec.composition or "tecido padrão"
    
    # Build POMs (Pontos de Medida) list with available measurements
    poms = []
    pom_counter = 1
    
    measurement_poms = {
        'body_length': 'Comprimento total (HPS até barra)',
        'bust': 'Largura peito (1 cm abaixo da cava, half chest)',
        'hem_width': 'Largura barra (hem width, half)',
        'shoulder_to_shoulder': 'Ombro a ombro (ponto externo a externo)',
        'neckline_depth': 'Abertura decote/gola (profundidade a partir do HPS)',
        'sleeve_length': 'Comprimento manga (do ponto mais alto do ombro até punho)',
        'waist': 'Largura cintura (half)',
        'straight_armhole': 'Largura da cava (vertical)'
    }
    
    for field, description in measurement_poms.items():
        value = getattr(spec, field, None)
        if value:
            # Sanitize measurement value: remove existing "cm" unit to avoid duplication
            value_str = str(value).strip()
            if value_str.lower().endswith('cm'):
                value_str = value_str[:-2].strip()
            poms.append(f"  {pom_counter}. {description}: {value_str} cm")
            pom_counter += 1
    
    poms_text = "\n".join(poms) if poms else "  (usar medidas proporcionais padrão)"
    
    # Build constructive details
    constructive_details = []
    if spec.finishes:
        constructive_details.append(f"Acabamentos: {spec.finishes}")
    if spec.openings_details:
        constructive_details.append(f"Fechamentos: {spec.openings_details}")
    
    details_text = " | ".join(constructive_details) if constructive_details else "detalhes conforme análise visual"
    
    # Build visual reference section
    visual_section = ""
    if visual_description:
        visual_section = f"""
REFERÊNCIA VISUAL (BASE OBRIGATÓRIA PARA FIDELIDADE):
{visual_description}
"""
    
    # Build complete professional prompt with POMs and dimensions
    prompt = f"""TAREFA: A partir da imagem da peça, gere desenho técnico plano (flat sketch) vetorial DIMENSIONADO com todas as cotas e POMs, pronto para produção e ficha técnica profissional.

IMPORTANTE: Gerar a versão com medidas e cotagem completa (não a versão limpa sem medidas).

ENTRADAS:
- Tipo da peça: {garment_type}
- Tamanho-base para cotagem: {size_base}
- Material/composição: {material_info}
- Detalhes construtivos: {details_text}
{visual_section}

VISTAS OBRIGATÓRIAS:
- Frente e Costas (mesma escala), alinhadas VERTICALMENTE
- Manga em posição natural quando aplicável
- Detalhes ampliados (1:2 ou 1:3) para: gola/colarinho, punho, bolso, zíper, barra, cós, casas de botão
- Seções: mostrar em corte simples sobreposições (placket, vista) e espessuras (punho/barra quando aplicável)

ESTILO VISUAL:
- Fundo 100% branco (#FFFFFF); sem corpo/manequim/cabide
- Traço preto; espessuras: contorno 0,75pt, costuras/canelado 0,35pt, pesponto/linha tracejado 0,35pt
- Cinza 15-30% apenas para sobreposição/forro
- Simetria central indicada por linha ponto-traço (eixo central)
- Símbolos gráficos: botão (círculo 2-4mm), ilhós (anel), rebite (ponto sólido)

CONVENÇÕES DE COTAGEM (MEDIDAS E POMs):
- Linhas de cota: finas (0,35pt), com setas cheias
- Linhas de chamada perpendiculares, afastamento mínimo 3mm do contorno
- Texto de medida: sans-serif 8-9pt, sempre acima da linha de cota; unidade em cm
- Centro/espelhamento: indicar eixo central; usar "(x2)" quando medida refere-se a metade simétrica
- Cada POM numerado no desenho

PONTOS DE MEDIDA (POMs) OBRIGATÓRIOS:
{poms_text}

DETALHES CONSTRUTIVOS (incluir todos aplicáveis):
- Textura/padronagem: representar com traço técnico (nervuras, canelados, tranças quando aplicável)
- Golas/colarinho, punhos, barras, acabamentos (rebatido, vivo, overlock)
- Recortes, pences, pregas, franzidos, dobras funcionais
- Fechamentos: tipo (zíper invisível/nylon/metal, botões, colchetes), posição e quantidade
- Casas de botão: posição centrada, distância da borda e quantidade
- Bolsos: tipo (faca, chapa, embutido), dimensões relativas, tampas, vivos
- Cós/placket: largura, com/sem passantes, lado do abotoamento
- Etiquetas: localização (interna/externa)

NORMALIZAÇÃO DA IMAGEM:
- Corrigir perspectiva/distorções: alinhar eixo central
- Garantir simetria quando aplicável (espelhar quando necessário)
- Remover sombras/elementos que não pertencem à construção
- Todas as medidas em peça relaxada (sem esticar)

CRITÉRIOS DE ACEITAÇÃO:
- Todos os POMs numerados visíveis e legíveis no desenho
- Frente/Costas na mesma escala, perfeitamente centradas
- Eixo central indicado; simetria consistente
- Linhas de cota não colidem com textura/contornos (usar afastamentos adequados)
- Proporções consistentes com as medidas de referência
- Visual limpo e técnico para produção

NÃO FAZER (PROIBIDO):
- NÃO incluir modelo/sombra realista/gradiente
- NÃO omitir POMs de barra, punho, decote, botões quando aplicáveis
- NÃO usar gradientes ou texturas fotorrealistas
- NÃO estilizar com traço orgânico/artístico; manter técnico
- NÃO inventar detalhes não descritos na referência visual"""

    return prompt



def process_specification_with_openai(text_content):
    """Process specification text using OpenAI to extract structured data"""
    if not openai_client:
        print("OpenAI client not initialized")
        return None

    try:    
        prompt = """
        Analise o seguinte texto de ficha técnica de vestuário e extraia as informações estruturadas em formato JSON.
        
        Extraia as seguintes categorias:
        1. Identificação da Peça: ref_souq, description, collection, supplier, corner
        2. Informações Comerciais: target_price, store_month, delivery_cd_month
        3. Prazos e Entregas: tech_sheet_delivery_date, pilot_delivery_date, showcase_for
        4. Equipe Envolvida: stylists
        5. Matéria-Prima e Aviamentos: composition, colors, tags_kit
        6. Especificações Técnicas: pilot_size, body_length, sleeve_length, hem_width, shoulder_to_shoulder, bust, waist, straight_armhole, neckline_depth, openings_details, finishes
        7. Design e Estilo: technical_drawing, reference_photos, specific_details
        
        Para datas, use formato YYYY-MM-DD. Se uma informação não estiver disponível, use null.
        
        Texto da ficha técnica:
        """ + text_content

        # Using gpt-4-turbo for JSON mode support
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role":
                "system",
                "content":
                "Você é um especialista em análise de fichas técnicas de vestuário. Extraia informações estruturadas e retorne SOMENTE em formato JSON válido, sem texto adicional."
            }, {
                "role": "user",
                "content": prompt
            }],
            response_format={"type": "json_object"},
            max_tokens=2000)

        content = response.choices[0].message.content
        if content:
            try:
                parsed_json = json.loads(content)
                return parsed_json
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {je}")
                return None
        else:
            return None
    except Exception as e:
        print(f"Error processing with OpenAI: {e}")
        return None


# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    if user.is_admin:
        # Admin dashboard
        total_users = User.query.count()
        total_specs = Specification.query.count()
        recent_specs = Specification.query.order_by(
            Specification.created_at.desc()).limit(10).all()
        return render_template('admin_dashboard.html',
                               total_users=total_users,
                               total_specs=total_specs,
                               recent_specs=recent_specs)
    else:
        # User dashboard
        user_specs = Specification.query.filter_by(user_id=user.id).order_by(
            Specification.created_at.desc()).all()
        return render_template('user_dashboard.html',
                               specifications=user_specs)


@app.route('/manage_users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)


@app.route('/create_user', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.is_admin = bool(form.is_admin.data)
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
            flash(f'Usuário {user.username} criado com sucesso!')
            return redirect(url_for('manage_users'))
        except Exception as e:
            db.session.rollback()
            flash(
                'Erro ao criar usuário. Verifique se o nome de usuário e email são únicos.'
            )

    return render_template('create_user.html', form=form)


@app.route('/upload_pdf', methods=['GET', 'POST'])
@login_required
def upload_pdf():
    form = UploadPDFForm()
    if request.method == 'POST' and form.validate_on_submit():
        try:
            file = form.pdf_file.data
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Create specification record
            spec = Specification()
            spec.user_id = session['user_id']
            spec.pdf_filename = filename
            spec.processing_status = 'processing'
            spec.created_at = datetime.now()

            db.session.add(spec)
            db.session.commit()

            # Process PDF asynchronously (in a real app, use Celery or similar)
            process_pdf_specification(spec.id, file_path)

            flash('PDF enviado com sucesso! O processamento está em andamento.')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error in upload_pdf: {e}")
            import traceback
            traceback.print_exc()
            flash('Erro ao processar o arquivo PDF. Por favor, tente novamente ou contate o suporte.')
            return render_template('upload_pdf.html', form=form)

    return render_template('upload_pdf.html', form=form)


@app.route('/specification/<int:id>')
@login_required
def view_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    return render_template('view_specification.html', specification=spec)


@app.route('/download_pdf/<int:id>')
@login_required
def download_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path,
                             as_attachment=True,
                             download_name=spec.pdf_filename)
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao baixar o arquivo PDF.')
        return redirect(url_for('view_specification', id=id))


@app.route('/view_pdf/<int:id>')
@login_required
def view_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='application/pdf')
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('view_specification', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo PDF.')
        return redirect(url_for('view_specification', id=id))


@app.route('/drawing/<int:id>')
@login_required
def view_drawing(id):
    """Serve the generated technical drawing image"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    if not spec.technical_drawing_url:
        flash('Desenho técnico não encontrado.')
        return redirect(url_for('view_specification', id=id))

    try:
        # Check if it's a legacy external URL (HTTPS) or new local filename
        if spec.technical_drawing_url.startswith('http://') or spec.technical_drawing_url.startswith('https://'):
            # Legacy URL from DALL-E 3 - redirect to external URL
            return redirect(spec.technical_drawing_url)
        else:
            # New local file from GPT-Image-1
            drawing_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.technical_drawing_url)
            if os.path.exists(drawing_path):
                return send_file(drawing_path, mimetype='image/png')
            else:
                flash('Arquivo de desenho não encontrado.')
                return redirect(url_for('view_specification', id=id))
    except Exception as e:
        print(f"Error serving drawing: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao carregar desenho técnico.')
        return redirect(url_for('view_specification', id=id))


@app.route('/specification/<int:id>/generate_drawing', methods=['POST'])
@login_required
def generate_technical_drawing(id):
    """Generate technical drawing using GPT-Image-1"""
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    if not openai_client:
        flash('OpenAI não está configurado. Contate o administrador.')
        return redirect(url_for('view_specification', id=id))

    try:
        # Get PDF file path
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        
        # Extract images from PDF
        images = extract_images_from_pdf(file_path)
        
        # Analyze images with GPT-4 Vision to get visual description
        visual_desc = analyze_images_with_gpt4_vision(images) if images else None
        
        # Build prompt with specification data and visual description
        prompt = build_technical_drawing_prompt(spec, visual_desc)

        # Generate image using GPT-Image-1 with high quality for maximum detail
        response = openai_client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",  # GPT-Image-1 supports up to 4096x4096
            quality="high",  # High quality for better detail and precision
            n=1
        )

        # GPT-Image-1 returns base64 by default
        import base64
        import uuid
        
        # Decode the base64 image
        image_data = base64.b64decode(response.data[0].b64_json)
        
        # Generate unique filename
        drawing_filename = f"drawing_{spec.id}_{uuid.uuid4().hex[:8]}.png"
        drawing_path = os.path.join(app.config['UPLOAD_FOLDER'], drawing_filename)
        
        # Save image to disk
        with open(drawing_path, 'wb') as f:
            f.write(image_data)
        
        # Save the filename (we'll serve it via a route)
        spec.technical_drawing_url = drawing_filename
        db.session.commit()

        flash('Desenho técnico gerado com sucesso!')
        return redirect(url_for('view_specification', id=id))

    except Exception as e:
        print(f"Error generating technical drawing: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao gerar desenho técnico. Tente novamente.')
        return redirect(url_for('view_specification', id=id))


@app.route('/specification/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_specification(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    # Allow access if user is admin or owns the specification
    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard'))

    form = SpecificationForm(obj=spec)
    if form.validate_on_submit():
        form.populate_obj(spec)
        try:
            db.session.commit()
            flash('Especificação atualizada com sucesso!')
            return redirect(url_for('view_specification', id=spec.id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar especificação.')

    return render_template('edit_specification.html',
                           form=form,
                           specification=spec)


@app.route('/specification/<int:id>/delete', methods=['POST'])
@login_required
def delete_specification(id):
    try:
        spec = Specification.query.get_or_404(id)
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('Sessão inválida. Por favor, faça login novamente.')
            return redirect(url_for('login'))

        # Allow access if user is admin or owns the specification
        if not user.is_admin and spec.user_id != user.id:
            flash('Acesso negado.')
            return redirect(url_for('dashboard'))

        # Delete associated file if it exists
        file_path = os.path.join(app.config['UPLOAD_FOLDER'],
                                 spec.pdf_filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        db.session.delete(spec)
        db.session.commit()
        flash('Especificação excluída com sucesso!')
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao excluir especificação {id}: {e}")
        flash('Erro ao excluir especificação. Tente novamente.')

    return redirect(url_for('dashboard'))


@app.route('/user/<int:id>/delete', methods=['POST'])
@admin_required
def delete_user(id):
    user = User.query.get_or_404(id)

    # Don't allow deleting the current admin user
    current_user = User.query.get(session['user_id'])
    if not current_user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('login'))

    if user.id == current_user.id:
        flash('Não é possível excluir seu próprio usuário.')
        return redirect(url_for('manage_users'))  # Redirect to manage users page