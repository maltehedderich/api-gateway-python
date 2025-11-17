#!/bin/bash
set -e

# Build Lambda deployment package for API Gateway
# This script creates a ZIP file with the application code and dependencies

echo "Building Lambda deployment package..."

# Configuration
BUILD_DIR="build/lambda"
PACKAGE_NAME="lambda-package.zip"
PYTHON_VERSION="3.12"

# Clean previous build
echo "Cleaning previous build..."
rm -rf "$BUILD_DIR"
rm -f "$PACKAGE_NAME"

# Create build directory
mkdir -p "$BUILD_DIR"

# Install dependencies to build directory
echo "Installing dependencies..."
uv pip install \
  --target "$BUILD_DIR" \
  --python-version "$PYTHON_VERSION" \
  --no-cache-dir \
  aiohttp>=3.9.0 \
  pyyaml>=6.0 \
  pydantic>=2.5.0 \
  prometheus-client>=0.19.0 \
  python-dotenv>=1.0.0 \
  cryptography>=41.0.0 \
  boto3>=1.34.0 \
  mangum>=0.17.0

# Copy application code to build directory
echo "Copying application code..."
cp -r src/gateway "$BUILD_DIR/"

# Remove unnecessary files to reduce package size
echo "Optimizing package size..."
cd "$BUILD_DIR"

# Remove __pycache__, .pyc, .pyo files
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
find . -type f -name "*.pyi" -delete

# Remove test files
find . -type d -name tests -exec rm -rf {} + 2>/dev/null || true
find . -type d -name test -exec rm -rf {} + 2>/dev/null || true

# Remove documentation
find . -type f -name "*.md" -delete
find . -type f -name "*.rst" -delete

# Remove examples
find . -type d -name examples -exec rm -rf {} + 2>/dev/null || true

# Remove .dist-info directories (but keep them for now, needed by some packages)
# find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true

cd -

# Create ZIP package
echo "Creating ZIP package..."
cd "$BUILD_DIR"
zip -r "../../$PACKAGE_NAME" . -q
cd -

# Get package size
PACKAGE_SIZE=$(du -h "$PACKAGE_NAME" | cut -f1)

echo "✅ Lambda package built successfully!"
echo "📦 Package: $PACKAGE_NAME"
echo "📏 Size: $PACKAGE_SIZE"
echo ""
echo "Next steps:"
echo "1. Review package contents: unzip -l $PACKAGE_NAME | less"
echo "2. Test locally: python -m gateway.lambda_handler"
echo "3. Deploy with Terraform: cd terraform && terraform apply"
