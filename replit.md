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

### October 23, 2025 - Professional Technical Drawing Prompt (Industry Standard)
- **Comprehensive Professional Specifications**: Implemented complete industry-standard technical flat sketch specifications
  - **Required Views**: Front and back views aligned VERTICALLY (same scale, centered), with enlarged details (1:2 or 1:3) for collar, cuffs, pockets, zipper, hem, waistband
  - **Visual Style**: 100% white background (#FFFFFF); pure black line art; no model, mannequin, or hanger
  - **Line Standards**: 
    * Outline: continuous line (0.75pt)
    * Internal seams: fine continuous line (0.35pt)
    * Topstitching: short dashed line
    * Fold/turn: dash-dot line
  - **Construction Details**: Collars/necklines, cuffs, hems, finishes (flat-felled, piping, overlock), cutouts, darts, pleats, gathers, functional folds
  - **Closures**: Zippers (invisible/nylon/metal), buttons, snaps, ties - with length and position
  - **Pockets**: Type (slash, patch, inset), relative dimensions, flaps, piping
  - **Waistband/Belt**: with/without belt loops, quantity and position
  - **Labels/Branding**: location (internal/external)
  - **Neutral Gray (10-30%)**: ONLY for indicating overlap/volume/lining
  - **Graphic Symbols**: Button (circle 2-4mm), eyelet (ring), rivet (solid dot)
  - **Directional Arrows**: Simple arrows indicating button direction, zipper opening, pleat/gather direction (without text labels)
  - **Image Normalization**: Corrects perspective/distortions, aligns central axis, ensures symmetry
  - **Strict Prohibitions**: No model/mannequin/hanger, no gradients/realistic textures, no organic/artistic styling, no invented details
  - **Permitted Elements**: Graphic symbols and simple directional arrows; NO dimensional measurements, NO text legends, NO descriptive callouts

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
6. System builds specialized prompt combining visual description + extracted measurements
7. GPT-Image-1 generates professional flat sketch (1024x1024, high quality, line art style) based on actual reference images
8. System decodes base64 response and saves image locally as `drawing_{id}_{uuid}.png`
9. Database stores filename; image served via `/drawing/<id>` route with access control
10. Users can view, regenerate, or download technical drawings as needed

**Key Innovations:** 
- Uses **real images from PDFs** as references, analyzed by GPT-4 Vision, to ensure technical drawings match the actual garment instead of "inventing" details
- **Local storage** eliminates dependency on temporary external URLs and provides better control over assets
- **Backward compatibility** ensures existing specifications with DALL-E 3 URLs continue to work seamlessly