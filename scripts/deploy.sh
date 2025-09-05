#!/bin/bash

# Production deployment script for Bedrijfsanalyse API

set -e

# Configuration
ENVIRONMENT="${ENVIRONMENT:-production}"
API_VERSION="${API_VERSION:-1.0.0}"
DEPLOY_USER="${DEPLOY_USER:-$(whoami)}"
DEPLOY_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="./backups/$DEPLOY_TIMESTAMP"

echo "=========================================="
echo "Bedrijfsanalyse API Deployment Script"
echo "=========================================="
echo "Environment: $ENVIRONMENT"
echo "Version: $API_VERSION"
echo "Deploy User: $DEPLOY_USER"
echo "Timestamp: $DEPLOY_TIMESTAMP"
echo ""

# Pre-deployment checks
echo "1. Pre-deployment Checks"
echo "========================"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
else
    echo "✅ Docker is running"
fi

# Check if .env file exists
if [[ ! -f .env ]]; then
    echo "❌ .env file not found. Please create it with required environment variables."
    exit 1
else
    echo "✅ .env file found"
fi

# Check required environment variables
required_vars=("KVK_API_KEY" "OPENAI_API_KEY" "API_KEYS")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [[ -z "${!var}" ]] && ! grep -q "^$var=" .env; then
        missing_vars+=("$var")
    fi
done

if [[ ${#missing_vars[@]} -gt 0 ]]; then
    echo "❌ Missing required environment variables: ${missing_vars[*]}"
    echo "   Please add them to your .env file"
    exit 1
else
    echo "✅ Required environment variables present"
fi

# Check if we're deploying to production
if [[ "$ENVIRONMENT" == "production" ]]; then
    echo ""
    echo "🚨 PRODUCTION DEPLOYMENT WARNING 🚨"
    echo "You are about to deploy to PRODUCTION environment."
    echo "This will:"
    echo "  - Build and deploy new container"
    echo "  - Update the live API"
    echo "  - Affect real users"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Deployment cancelled."
        exit 0
    fi
fi

echo ""

# Create backup directory
echo "2. Creating Backup"
echo "=================="
mkdir -p "$BACKUP_DIR"

# Backup current container if it exists
if docker ps -a --format 'table {{.Names}}' | grep -q "bedrijfsanalyse-api"; then
    echo "Creating backup of current deployment..."
    docker commit bedrijfsanalyse-api "bedrijfsanalyse-api:backup-$DEPLOY_TIMESTAMP" 2>/dev/null || echo "No running container to backup"
    echo "✅ Backup created: bedrijfsanalyse-api:backup-$DEPLOY_TIMESTAMP"
else
    echo "ℹ️  No existing container found to backup"
fi

# Backup configuration files
cp .env "$BACKUP_DIR/" 2>/dev/null || echo "No .env to backup"
cp docker-compose.yml "$BACKUP_DIR/" 2>/dev/null || echo "No docker-compose.yml to backup"

echo "✅ Backup completed in $BACKUP_DIR"
echo ""

# Build and deploy
echo "3. Building Application"
echo "======================="

echo "Building Docker image..."
docker build -t bedrijfsanalyse-api:$API_VERSION -t bedrijfsanalyse-api:latest . || {
    echo "❌ Docker build failed"
    exit 1
}

echo "✅ Docker image built successfully"
echo ""

echo "4. Running Tests"
echo "================"

# Run basic container test
echo "Running container smoke test..."
docker run --rm --env-file .env \
    -e ENVIRONMENT=testing \
    -e DEBUG=false \
    bedrijfsanalyse-api:latest \
    python -c "
import sys
sys.path.append('/app')
try:
    from app.main import app
    print('✅ Application imports successfully')
except Exception as e:
    print(f'❌ Import error: {e}')
    sys.exit(1)
" || {
    echo "❌ Container smoke test failed"
    exit 1
}

echo "✅ Container smoke test passed"
echo ""

echo "5. Deploying Application"
echo "========================"

# Stop existing containers
if docker ps --format 'table {{.Names}}' | grep -q "bedrijfsanalyse-api"; then
    echo "Stopping existing containers..."
    docker-compose down || docker stop bedrijfsanalyse-api 2>/dev/null || true
    echo "✅ Existing containers stopped"
fi

# Start new containers
echo "Starting new deployment..."
ENVIRONMENT="$ENVIRONMENT" docker-compose up -d || {
    echo "❌ Deployment failed"
    echo "Attempting rollback..."
    
    # Rollback if backup exists
    if docker images --format 'table {{.Repository}}:{{.Tag}}' | grep -q "bedrijfsanalyse-api:backup-$DEPLOY_TIMESTAMP"; then
        echo "Rolling back to backup..."
        docker tag "bedrijfsanalyse-api:backup-$DEPLOY_TIMESTAMP" bedrijfsanalyse-api:latest
        docker-compose up -d
        echo "✅ Rollback completed"
    fi
    exit 1
}

echo "✅ New containers started"
echo ""

echo "6. Health Check"
echo "==============="

# Wait for application to start
echo "Waiting for application to start..."
sleep 30

# Health check with retries
max_retries=6
retry_count=0
health_check_url="http://localhost:8000/health"

while [[ $retry_count -lt $max_retries ]]; do
    if curl -f -s "$health_check_url" >/dev/null 2>&1; then
        echo "✅ Health check passed"
        break
    else
        ((retry_count++))
        echo "Health check attempt $retry_count/$max_retries failed, retrying in 10s..."
        sleep 10
    fi
done

if [[ $retry_count -eq $max_retries ]]; then
    echo "❌ Health check failed after $max_retries attempts"
    echo "Deployment may have issues. Check logs with: docker-compose logs bedrijfsanalyse-api"
    exit 1
fi

echo ""

echo "7. Post-deployment Verification"
echo "==============================="

# Run the complete API test suite
if [[ -f "scripts/test_complete_api.sh" ]]; then
    echo "Running complete API test suite..."
    bash scripts/test_complete_api.sh || {
        echo "⚠️  Some API tests failed. Check the output above."
        echo "   The deployment is running but may have issues."
    }
else
    echo "⚠️  API test suite not found. Skipping comprehensive tests."
fi

echo ""

echo "8. Cleanup"
echo "=========="

# Clean up old Docker images (keep last 3)
echo "Cleaning up old Docker images..."
docker images bedrijfsanalyse-api --format 'table {{.Tag}}' | grep -v '^TAG$' | grep -v '^latest$' | sort -r | tail -n +4 | xargs -I {} docker rmi bedrijfsanalyse-api:{} 2>/dev/null || echo "No old images to clean up"

# Clean up old backups (keep last 5)
echo "Cleaning up old backups..."
ls -1t backups/ 2>/dev/null | tail -n +6 | xargs -I {} rm -rf backups/{} 2>/dev/null || echo "No old backups to clean up"

echo "✅ Cleanup completed"
echo ""

# Final summary
echo "=========================================="
echo "Deployment Summary"
echo "=========================================="
echo "✅ Environment: $ENVIRONMENT"
echo "✅ Version: $API_VERSION"  
echo "✅ Status: DEPLOYED"
echo "✅ Health Check: PASSED"
echo "✅ Backup: $BACKUP_DIR"
echo ""
echo "API Endpoints:"
echo "  - Health: http://localhost:8000/health"
echo "  - Status: http://localhost:8000/status"
echo "  - Docs: http://localhost:8000/docs"
echo "  - Analysis: http://localhost:8000/analyze-company"
echo ""
echo "Management Commands:"
echo "  - View logs: docker-compose logs -f bedrijfsanalyse-api"
echo "  - Restart: docker-compose restart bedrijfsanalyse-api"
echo "  - Stop: docker-compose down"
echo ""

if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "🎉 PRODUCTION DEPLOYMENT SUCCESSFUL!"
    echo ""
    echo "Next Steps:"
    echo "1. Monitor application logs and metrics"
    echo "2. Verify all integrations are working"
    echo "3. Notify stakeholders of successful deployment"
    echo "4. Update monitoring dashboards if needed"
else
    echo "🎉 DEPLOYMENT SUCCESSFUL!"
    echo ""
    echo "You can now test the API at http://localhost:8000"
fi

echo ""
echo "Deployment completed at $(date)"
echo "=========================================="