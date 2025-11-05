# Overview

This Flask-based platform manages technical specifications for the fashion/textile industry. It processes PDF files and image files (JPG, PNG, JPEG) containing technical specs using OpenAI's API for OCR and structured data extraction. A key feature is AI-powered technical drawing generation using GPT-Image-1, which automatically creates professional clean flat sketches based on extracted specifications and visual analysis of garment images. The system includes role-based access control for users and administrators, alongside comprehensive activity tracking.

## Recent Changes (November 5, 2025)
- **Desenho Técnico Simplificado**: Geração de desenhos técnicos agora produz APENAS flat sketches limpos SEM medidas.
  - Removida toda lógica condicional de has_measurements
  - Prompt sempre gera desenhos SEM dimensões, POMs ou cotas
  - Foco em esboço visual limpo e profissional da peça
  - Mantém análise visual estruturada GPT-4o Vision para detalhes construtivos
  - Elimina poluição visual de números e linhas de cotagem
- **Replit Object Storage Integration**: Migração de armazenamento de desenhos técnicos para persistência cloud.
  - Desenhos técnicos agora salvos no Replit Object Storage ao invés do filesystem local
  - URLs públicas permanentes e acessíveis de qualquer dispositivo
  - Fallback automático para filesystem local se Object Storage falhar
  - Rotas atualizadas: `/drawing/<int:id>` e `/drawing/<path:filename>` com suporte a Object Storage
  - Templates atualizados para usar `url_for('view_drawing')` consistentemente
  - Script de migração (`migrate_drawings.py`) para mover desenhos existentes
  - Biblioteca `replit.object-storage` instalada e integrada
  - Estrutura de pastas: `technical-drawings/drawing_<id>_<hash>.png`
- **Galeria de Desenhos Técnicos**: Nova página dedicada para visualizar todos os desenhos técnicos gerados.
  - Nova rota /technical-drawings com filtros (busca, coleção, fornecedor) e paginação (12 itens/página)
  - Template technical_drawings.html com grid responsivo de cards
  - **Modal Lightbox**: Clique no desenho para visualizar em tela cheia dentro da galeria
  - Animações suaves de fade-in e zoom-in
  - Botão "Ver Detalhes Completos" na modal para acessar ficha técnica
  - Botão "Ver Detalhes" em cada card para navegação direta
  - Atalho ESC para fechar a modal
  - Exibição de desenho, nome/descrição, REF, badges de coleção e fornecedor
  - Busca nos campos: description, ref_souq, collection
  - Filtros por coleção e fornecedor com dropdowns dinâmicos
  - Paginação preservando parâmetros de busca/filtros
  - Empty state para quando não há desenhos gerados
  - Role-based access: admins veem todos, stylists veem apenas os seus
  - Link "Desenhos Técnicos" adicionado na sidebar de todos os templates
  - Design dark theme consistente: #0a0e1a background, #1e2538 cards, #2563eb accent
- **User Settings & Profile Management**: Complete settings page with modern dark theme interface.
  - New /settings route with GET/POST handling, login protection, and form validation
  - SettingsForm with username, email, and password change functionality
  - Uniqueness validation for username and email before updates
  - Profile card with avatar initials matching user branding
  - Settings submenu with Meu Perfil, Segurança, and Preferências sections
  - Flash messaging for success/error feedback on profile updates
  - Transactional database updates with rollback safety
- **Sidebar Navigation Controls**: Settings and logout buttons added across all templates.
  - Settings button (gear icon) linking to /settings
  - Logout button (red sign-out icon) linking to /logout
  - Consistent dark theme styling (.settings-btn, .logout-btn classes)
  - Updated templates: user_dashboard, upload_pdf, collections, view_collection, view_specification, edit_specification
  - Settings section positioned above user profile in sidebar
  - Hover states and visual feedback matching application design language
- **Modern Login Page**: Redesigned login.html with StyleSheet branding and professional dark theme.
  - Centered card layout with gradient blue CTA button
  - StyleSheet logo with blue icon and white text
  - "Bem-vindo(a) de volta!" heading with Portuguese localization
  - Remember me checkbox and "Esqueceu a senha?" link
  - "Crie uma agora" registration link
  - Dark theme colors: #0a0e1a background, #1e2538 card, #2563eb accent

## Previous Changes (November 4, 2025)
- **Collections Management System**: Complete end-to-end collection management feature with modern dark theme interface.
  - New Collection model in database (name, description, status, cover_image, user_id)
  - Relationship between Specification and Collection via collection_id foreign key
  - /collections page with grid of collection cards, search functionality, and filters
  - Modal interface for creating new collections with form validation
  - /collection/<id> page to view all pieces in a specific collection
  - Collection status tracking (em_desenvolvimento, finalizada)
  - Sidebar navigation updated across all pages with functional "My Collections" link
  - Role-based access: admins see all collections, stylists see only their own
  - **Collection Linking in Forms**: Added dropdown selector in upload and edit forms to link specifications to existing collections
  - Dynamic dropdown population based on user role (admins see all, stylists see own)
  - Optional linking: users can create specs without assigning to a collection (null collection_id)
  - Consistent dark theme (#0a0e1a, #1e2538, #2a3348) matching rest of application
- **Modern Edit Specification Page**: Completely redesigned edit_specification.html with professional dark theme and improved UX.
  - Two-column layout: form fields on left, product image preview on right (380px sticky)
  - Card-based organization: Informações Gerais, Detalhes e Materiais, Medidas (Tamanho Piloto), Informações Comerciais, Prazos e Entregas, Equipe e Design
  - All WTForms fields properly integrated for correct data persistence
  - Clean, modern interface with Cancelar and Salvar Alterações action buttons
  - Fixed 240px left sidebar matching other modern pages
  - Dark theme colors: #0a0e1a background, #1e2538 cards, #2a3348 accents
  - Standalone template (not extending base.html) for full design control, consistent with view_specification.html approach
- **Sidebar Navigation on Specification Page**: Added consistent sidebar navigation to view_specification.html matching dashboard design.
  - Fixed 240px left sidebar with StyleFlow logo and navigation menu
  - Menu items: Dashboard (active/highlighted), My Collections, Suppliers, Analytics
  - User profile display at bottom with avatar, name, and role
  - Main content area adjusted with left margin to accommodate sidebar
  - Consistent dark theme across entire interface
- **Modern Specification Details Page**: Completely redesigned view_specification.html with professional dark theme.
  - Two-column layout: sticky product image section (380px) on left, detailed specs on right
  - Tabbed interface for Medidas, Materiais, Observações with smooth transitions
  - Professional measurements table with P, M, G, GG columns (currently displays pilot size data)
  - Dark theme colors: #0a0e1a background, #1e2538 cards, #2a3348 accents
  - Large product image display (pdf_thumbnail or technical_drawing) with action buttons
  - Clean information hierarchy with proper spacing and typography
  - All existing features preserved: PDF viewer, technical drawing generation, edit/delete actions
- **PDF Thumbnail Previews**: Dashboard cards now display actual PDF preview thumbnails generated from the first page using PyMuPDF.
  - New `pdf_thumbnail` field in Specification model stores thumbnail paths
  - Automatic thumbnail generation during PDF upload and processing
  - Thumbnails stored in `static/thumbnails/` directory at 300px width
  - Migration script (`generate_thumbnails_script.py`) for existing PDFs (5 thumbnails generated successfully)
  - Priority display: pdf_thumbnail → technical_drawing_url → product_image → fallback icon
- **Dark Theme Applied to Main Templates**: Applied professional dark theme directly to existing templates (user_dashboard.html, admin_dashboard.html, upload_pdf.html) instead of creating separate files.
- **Product Image Display in Cards**: Dashboard cards now display product images from both legacy (`drawing_XX_HASH.png`) and new (`/static/product_images/product_XX_HASH.png`) formats with proper fallback to Font Awesome icon.
- **Image Styling**: Product images displayed with 200px height, object-fit: cover for proper aspect ratio, and centered positioning.
- **Product Grid View**: Cards display product images, name, collection, supplier, and status badges with color-coded workflow states.
- **Advanced Filtering**: Multi-criteria filtering by collection, supplier, status (Draft, In Development, Approved, In Production) with 100-result limit for performance.
- **Full-Text Search**: Search functionality across product names, codes, and collections with real-time results.
- **Product Status Workflow**: Added `status` field to track product lifecycle (draft → in_development → approved → in_production).
- **Supplier Management**: Added `supplier` field to upload form and database for supplier-based organization.
- **Automatic Product Images**: System saves largest extracted PDF image or uploaded image file to static/product_images/ for display in dashboard cards.
- **Sidebar Navigation**: Professional sidebar with Dashboard, My Collections, Suppliers, Analytics sections and user profile display.
- **Role-Based Dashboard**: Stylists see only their specifications; admins see all with full filtering capabilities.
- **Clean Code Structure**: Removed temporary template files (dashboard_new.html, upload_new.html) and routes after applying design to existing templates.

## Previous Changes (October 28, 2025)
- **Indexed ColorSpace Support**: Fixed PDF image extraction to properly handle Indexed ColorSpace with palette lookup.
- **Pattern Rendering in Drawings**: Enhanced technical drawing prompts for accurate pattern representation.
- **Image Upload Support**: Extended upload to accept JPG, PNG, JPEG files with GPT-4o Vision analysis.
- **Loading Indicators**: Added visual feedback during processing operations.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## UI/UX Decisions
- **Frontend**: Jinja2 templates, Bootstrap 5 for responsive design.
- **Styling**: Custom CSS, Font Awesome icons.
- **Forms**: Flask-WTF for secure handling, CSRF protection.
- **File Upload**: Drag-and-drop interface with client-side validation.

## Technical Implementations
- **Web Framework**: Flask with a modular route structure.
- **Database ORM**: SQLAlchemy for database abstraction.
- **Authentication**: Session-based, with Werkzeug for password hashing.
- **File Processing**: PyPDF2 for PDF text and image extraction.
- **AI Processing**: OpenAI API for data parsing, vision analysis, and image generation.
- **Security**: CSRF protection, secure filename handling, file size limits.

## System Design Choices
- **Data Storage**: SQL database for primary data, local filesystem for uploaded PDFs and generated drawings.
- **Session Management**: Flask sessions for user state.
- **Authentication & Authorization**: Two-tier user roles (regular, admin) with decorator-based access control.
- **AI Integration Workflow**:
    1. PDF upload and data extraction (GPT-4-Turbo).
    2. Image extraction from PDF (PyPDF2).
    3. Visual analysis of garment images (GPT-4o Vision) to produce structured JSON.
    4. Technical drawing prompt construction using extracted data and visual analysis.
    5. Professional flat sketch generation with dimensions (GPT-Image-1).
    6. Local storage of generated drawings and database record of filenames.

## Feature Specifications
- **Data Extraction**: Transforms unstructured PDF content into structured records (product identification, commercial info, deadlines, materials, technical measurements).
- **Technical Drawing Generation**: Produces production-ready, dimensioned flat sketches (flat dimensionado) with:
    - Front and back views, aligned vertically, to scale.
    - Numbered Measurement Points (POMs) with tolerances.
    - Professional dimensioning (cotagem) with specific line weights, arrow styles, and text positioning.
    - Technical representation of textures, constructions, and details.
    - Local storage of generated drawings (base64 decoded).
    - Image Normalization: Corrects perspective, aligns central axis, ensures symmetry.
- **Output**: Generates a single, dimensioned image per request; a clean (non-dimensioned) version would require a separate generation workflow.
- **Key Innovations**: Utilizes actual images from PDFs for AI analysis, integrates POMs from specification data, adheres to professional cotagem standards, and uses local storage for generated assets.

# External Dependencies

- **OpenAI API**:
    - **GPT-4-Turbo**: Text analysis and structured data extraction from PDFs.
    - **GPT-4o Vision**: Analyzing garment images from PDFs to describe construction details in structured JSON.
    - **GPT-Image-1**: Generating professional technical drawings (flat sketches) based on specifications and visual analysis.
- **SQL Database**: Configured via `SQLALCHEMY_DATABASE_URI`.
- **Environment Variables**: `SESSION_SECRET` for session security, `OPENAI_API_KEY` for AI processing.