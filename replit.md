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
  - GPT-Image-1 for generating professional technical drawings (flat sketches) from specifications
- **Database**: SQL database connection via SQLALCHEMY_DATABASE_URI
- **Environment Variables**: SESSION_SECRET for session security, OPENAI_API_KEY for AI processing

## Recent Changes (October 21, 2025)

### Technical Drawing Generation Feature
- **Added GPT-Image-1 Integration**: Users can now automatically generate professional technical drawings (flat sketches) from specification data using OpenAI's latest image generation model
- **High-Quality Output**: Using quality="high" setting for maximum detail, superior text rendering, and better adherence to measurements
- **Resolution**: 1536x1024 pixels (maximum landscape format supported by GPT-Image-1)
- **Dynamic Prompt Building**: System intelligently constructs prompts using extracted measurements and technical details
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
4. System builds specialized prompt with extracted data
5. GPT-Image-1 generates professional flat sketch (1536x1024, high quality, line art style)
6. Generated image URL is stored and displayed in specification view
7. Users can regenerate or download technical drawings as needed

**GPT-Image-1 Advantages:**
- Superior text rendering for technical annotations
- Better understanding of technical specifications
- More accurate proportions and measurements
- Higher resolution output (up to 4096x4096 supported)
- Improved style consistency and detail quality