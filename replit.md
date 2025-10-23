# Overview

This is a Flask-based technical specification management platform designed for fashion/textile industry workflows. The system allows users to upload PDF files containing technical specifications (fichas técnicas) and uses OpenAI's API to extract structured information through OCR processing. The platform now includes AI-powered technical drawing generation using DALL-E 3, automatically creating professional flat sketches based on extracted specifications. Features include role-based access with admin controls for user management and comprehensive tracking of all user activities.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Frontend Architecture
- **Template Engine**: Jinja2 templates with Bootstrap 5 for responsive UI
- **Styling**: Custom CSS with Font Awesome icons for enhanced user experience
- **Forms**: Flask-WTF for secure form handling with CSRF protection
- **File Upload**: Drag-and-drop interface for PDF uploads with client-side validation

## Backend Architecture
- **Web Framework**: Flask with modular route structure
- **Database ORM**: SQLAlchemy for database abstraction and relationship management
- **Authentication**: Session-based authentication with password hashing using Werkzeug
- **File Processing**: PyPDF2 for PDF text extraction combined with OpenAI API for intelligent data parsing
- **Security**: CSRF protection, secure filename handling, and file size limits

## Data Storage Solutions
- **Primary Database**: SQL database (configured via DATABASE_URL environment variable)
- **File Storage**: Local filesystem storage for uploaded PDF files
- **Session Management**: Flask sessions for user state management

## Authentication and Authorization
- **User Roles**: Two-tier system with regular users and administrators
- **Access Control**: Decorator-based route protection (@admin_required)
- **Password Security**: Werkzeug password hashing for secure credential storage

## External Dependencies
- **OpenAI API**: 
  - GPT-4-Turbo for text analysis and extracting structured data from PDF content
  - GPT-4o Vision for analyzing garment images and describing construction details
  - GPT-Image-1 for generating professional technical drawings (flat sketches) from specifications
- **Database**: SQL database connection via SQLALCHEMY_DATABASE_URI
- **Environment Variables**: SESSION_SECRET for session security, OPENAI_API_KEY for AI processing

## Recent Changes

### October 23, 2025 - GPT-Image-1 Integration with Local File Storage
- **Upgraded to GPT-Image-1**: Replaced DALL-E 3 with OpenAI's latest GPT-Image-1 model for superior image quality
  - **Higher Quality**: Photorealistic results with 94% prompt adherence (vs 78% on DALL-E 3)
  - **Better Resolution**: Support for up to 4096x4096 pixels (currently using 1024x1024)
  - **Perfect Text Rendering**: Accurate text within images for labels and annotations
  - **Enhanced Fidelity**: Significantly better at following complex technical drawing specifications
- **Local File Storage**: Images now saved locally instead of relying on temporary external URLs
  - GPT-Image-1 returns base64-encoded images (no URL support)
  - System decodes base64 and saves as `drawing_{spec_id}_{uuid}.png` in `uploads/` folder
  - Database stores only the filename, reducing dependency on external services
  - Created `/drawing/<id>` route to serve images with proper access control
- **Backward Compatibility**: Seamless support for legacy DALL-E 3 URLs
  - Route detects if `technical_drawing_url` starts with `http://` or `https://`
  - Legacy URLs redirect to external OpenAI storage
  - New filenames serve from local storage via `send_file()`
  - Zero breaking changes for existing specifications

### October 23, 2025 - Professional Technical Drawing with POMs and Dimensions
- **Production-Ready Technical Specifications**: Implemented professional flat sketch with measurements, dimensions, and POMs (Pontos de Medida)
  - **Required Views**: Front and back aligned VERTICALLY (same scale), sleeve in natural position, enlarged details (1:2 or 1:3) for collar, cuffs, pockets, zipper, hem, waistband, buttonholes
  - **Visual Style**: 100% white background; pure black line art; no model/mannequin/hanger; central axis indicated with dash-dot line
  - **Line Standards**: 
    * Outline: 0.75pt continuous
    * Seams/ribbing: 0.35pt continuous
    * Topstitching: 0.35pt dashed
    * Fold/overlap: dash-dot line
  - **Dimension Conventions (POMs)**:
    * Dimension lines: thin (0.35pt) with filled arrows
    * Extension lines: perpendicular, minimum 3mm offset from contour
    * Measurement text: sans-serif 8-9pt, above dimension line, unit in cm
    * Symmetry notation: use "(x2)" for half-width measurements
    * Each POM numbered on drawing
  - **POMs (Measurement Points)**: 
    * Total length (HPS to hem)
    * Chest width (1cm below armhole, half chest)
    * Hem width (half)
    * Shoulder to shoulder (outside points)
    * Neckline/collar depth (from HPS)
    * Sleeve length (highest shoulder point to cuff, following curve)
    * Waist width (half)
    * Armhole width (vertical)
  - **Construction Details**: Technical representation of textures/patterns (ribs, cables, pleats), collars, cuffs, hems, finishes, cuts, darts, closures with type/position/quantity
  - **Sections/Cross-cuts**: Simple cross-sections showing overlaps (placket, facing) and thicknesses (cuff/hem when applicable)
  - **Neutral Gray (15-30%)**: ONLY for overlap/volume/lining
  - **Graphic Symbols**: Button (circle 2-4mm), eyelet (ring), rivet (solid dot)
  - **Image Normalization**: Corrects perspective, aligns central axis, ensures symmetry, measurements on relaxed garment
  - **Acceptance Criteria**: All POMs numbered and legible; front/back same scale; central axis marked; dimension lines don't collide with contours; proportions match reference measurements
  - **Strict Prohibitions**: No model/realistic shadows/gradients; no omission of hem/cuff/neckline/button POMs; no photorealistic textures; no organic/artistic styling; no invented details

### October 21, 2025 - Vision-Based Technical Drawing Generation
- **Added GPT-4o Vision Integration**: System now analyzes actual garment images from PDFs before generating technical drawings
- **Image Extraction**: PyPDF2 extracts up to 3 images from uploaded PDFs
- **Visual Analysis**: GPT-4o Vision provides detailed technical description of garment construction
- **Enhanced Prompt**: Combines visual description with extracted measurements for accurate DALL-E 3 generation
- **High-Quality Output**: Using quality="hd" setting for maximum detail and precision
- **Resolution**: 1792x1024 pixels (maximum landscape format)
- **Database Schema Update**: Added `technical_drawing_url` field to store generated image URLs
- **User Interface Enhancements**: 
  - New "Desenho Técnico" card in specification view
  - One-click generation button with progress indication
  - Image preview and regeneration options
  - Direct link to open drawings in new tab

## Core Functionality

The system processes technical specifications containing product identification, commercial information, delivery schedules, team assignments, materials, and technical measurements. The AI integration transforms unstructured PDF content into structured database records with fields for reference codes, descriptions, collections, suppliers, pricing, and detailed technical measurements.

**Technical Drawing Generation Workflow:**
1. User uploads PDF containing technical specifications
2. System extracts data using GPT-4-Turbo (measurements, materials, finishes)
3. User clicks "Gerar Desenho Técnico" button
4. System extracts up to 3 images from the PDF using PyPDF2
5. GPT-4o Vision analyzes images and generates detailed technical description of the garment
6. System builds specialized prompt combining visual description + extracted measurements + POMs
7. GPT-Image-1 generates professional flat sketch **dimensionado** (with dimensions and POMs) - 1024x1024, high quality
8. System decodes base64 response and saves image locally as `drawing_{id}_{uuid}.png`
9. Database stores filename; image served via `/drawing/<id>` route with access control
10. Users can view, regenerate, or download technical drawings as needed

**Output:** System generates the **dimensioned version** (flat dimensionado) with all measurements, POMs, and dimension lines - the most complete and production-ready version. 

**Note:** GPT-Image-1 generates one image per call. If a clean version (without dimensions) is needed, a separate generation workflow would be required.

**Key Innovations:** 
- Uses **real images from PDFs** as references, analyzed by GPT-4 Vision, to ensure technical drawings match the actual garment instead of "inventing" details
- **POMs (Pontos de Medida)** automatically numbered and integrated from specification data
- **Professional cotagem** with dimension lines, arrows, and measurement text following industry standards
- **Local storage** eliminates dependency on temporary external URLs and provides better control over assets
- **Backward compatibility** ensures existing specifications with DALL-E 3 URLs continue to work seamlessly