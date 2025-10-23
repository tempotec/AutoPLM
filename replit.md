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

### October 23, 2025 - GPT-Image-1 Integration
- **Upgraded to GPT-Image-1**: Replaced DALL-E 3 with OpenAI's latest GPT-Image-1 model for superior image quality
  - **Higher Quality**: Photorealistic results with 94% prompt adherence (vs 78% on DALL-E 3)
  - **Better Resolution**: Support for up to 4096x4096 pixels (currently using 1024x1024)
  - **Perfect Text Rendering**: Accurate text within images for labels and annotations
  - **Enhanced Fidelity**: Significantly better at following complex technical drawing specifications

### October 23, 2025 - Professional Technical Drawing Prompt
- **Upgraded Drawing Specifications**: Implemented industry-standard specifications for professional technical drawings
  - **Dual Views**: Front and back views side-by-side, horizontally aligned
  - **Line Art Style**: Pure 2D line art with uniform black lines, transparent fill, white background (#FFFFFF)
  - **Isolated Garment**: No model, mannequin, hanger, scenery, or reflections
  - **Construction Details**: Specific rendering of seam lines, topstitching, darts, collars, cuffs, hems, closures, pockets, pleats
  - **Strict Negatives**: No colors, shadows, gradients, 3D effects, text, numbers, annotations, or invented elements
  - **Professional Layout**: Landscape orientation (1792x1024), minimal margins, consistent line weight
  - **Maximum Fidelity**: Priority on absolute accuracy to GPT-4 Vision analysis and technical measurements

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
4. **NEW**: System extracts images from the PDF using PyPDF2
5. **NEW**: GPT-4o Vision analyzes images and generates detailed technical description of the garment
6. System builds specialized prompt combining visual description + extracted measurements
7. GPT-Image-1 generates professional flat sketch (1024x1024, high quality, line art style) based on actual reference images
8. Generated image URL is stored and displayed in specification view
9. Users can regenerate or download technical drawings as needed

**Key Innovation:** The system now uses **real images from PDFs** as references, analyzed by GPT-4 Vision, to ensure technical drawings match the actual garment instead of "inventing" details.