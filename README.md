# Avatar AI System - Serverless Setup Guide

## Overview
This guide deploys a **serverless, auto-scaling** 3D realistic AI Avatar system using Azure's managed services. This architecture is **cost-optimized**, **highly scalable**, and **production-ready** for 10K+ users.

## Phase 1: Serverless Infrastructure Setup (30 minutes)

### Prerequisites
1. **Azure Account** with subscription
2. **Local Development Environment:**
   - Azure CLI 2.0+
   - Terraform 1.0+
   - kubectl (Kubernetes CLI)
   - Docker Desktop
   - Helm 3.0+

### Step 1: Deploy Serverless Infrastructure
```bash
# Create project directory
mkdir avatar-ai-serverless
cd avatar-ai-serverless

# Save the terraform files from artifacts above:
# - main.tf (serverless infrastructure)
# - kubernetes.tf (AKS configuration)

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -out=tfplan

# Deploy infrastructure (15-20 minutes)
terraform apply tfplan
```

### Step 2: Configure Kubernetes Access
```bash
# Get AKS credentials
az aks get-credentials --resource-group $(terraform output -raw resource_group_name) \
  --name $(terraform output -raw aks_cluster_name)

# Verify connection
kubectl get nodes

# Install KEDA for advanced auto-scaling
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace keda-system --create-namespace

# Install Application Gateway Ingress Controller
helm repo add application-gateway-kubernetes-ingress https://appgwingress.blob.core.windows.net/ingress-azure-helm-package/
helm repo update
helm install ingress-azure application-gateway-kubernetes-ingress/ingress-azure \
  --namespace default \
  --set appgw.name=$(terraform output -raw application_gateway_name) \
  --set appgw.resourceGroup=$(terraform output -raw resource_group_name)
```

## Phase 2: Application Deployment (30 minutes)

### Step 1: Build and Push Container Images
```bash
# Get ACR credentials
ACR_NAME=$(terraform output -raw container_registry_url | cut -d'.' -f1)
az acr login --name $ACR_NAME

# Create application structure
mkdir -p src/{backend,frontend,docker}

# Save the core services and backend files from artifacts
# - src/backend/avatar_ai_services.py
# - src/backend/main.py
# - src/frontend/index.html

# Create Dockerfiles
cat > src/docker/Dockerfile.backend << 'EOF'
FROM nvidia/cuda:12.1-runtime-ubuntu22.04

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-pip python3.11-dev \
    ffmpeg libsndfile1 portaudio19-dev \
    curl git && \
    rm -rf /var/lib/apt/lists/*

# Set Python as default
RUN ln -s /usr/bin/python3.11 /usr/bin/python
RUN ln -s /usr/bin/pip3.11 /usr/bin/pip

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Azure specific packages
RUN pip install azure-storage-blob azure-identity redis[hiredis]

# Copy application code
COPY backend/ .

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000 8080

# Use gunicorn for production
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--timeout", "120"]
EOF

cat > src/docker/Dockerfile.frontend << 'EOF'
FROM nginx:alpine

# Copy static files
COPY frontend/ /usr/share/nginx/html/

# Configure nginx
RUN echo 'server { \
    listen 80; \
    location / { \
        root /usr/share/nginx/html; \
        index index.html; \
        try_files $uri $uri/ /index.html; \
    } \
    location /api/ { \
        proxy_pass http://avatar-ai-processor-service:8000; \
    } \
    location /ws/ { \
        proxy_pass http://avatar-ai-processor-service:8080; \
        proxy_http_version 1.1; \
        proxy_set_header Upgrade $http_upgrade; \
        proxy_set_header Connection "upgrade"; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
EOF

# Build and push images
docker build -f src/docker/Dockerfile.backend -t $ACR_NAME.azurecr.io/avatar-ai-backend:latest src/
docker push $ACR_NAME.azurecr.io/avatar-ai-backend:latest

docker build -f src/docker/Dockerfile.frontend -t $ACR_NAME.azurecr.io/avatar-ai-web:latest src/
docker push $ACR_NAME.azurecr.io/avatar-ai-web:latest
```

### Step 2: Configure Secrets and Environment
```bash
# Create namespace and secrets
kubectl create namespace avatar-ai

# Add your API keys to Kubernetes secrets
kubectl create secret generic avatar-ai-secrets \
  --from-literal=openai-api-key="your-openai-key-here" \
  --from-literal=did-api-key="your-did-key-here" \
  --from-literal=elevenlabs-api-key="your-elevenlabs-key-here" \
  --from-literal=azure-storage-key="$(terraform output -raw storage_account_key)" \
  --namespace avatar-ai

# Create configmap for application settings
kubectl create configmap avatar-ai-config \
  --from-literal=REDIS_URL="redis://$(terraform output -raw redis_hostname):6380" \
  --from-literal=DATABASE_URL="postgresql://avataraiuser:AvatarAI2025!@#@# Avatar AI System - Complete Setup Guide

## Overview
This guide will help you deploy a production-ready 3D realistic AI Avatar system that can handle 10K+ users with real-time speech-to-text, AI responses, text-to-speech, and lip-synced video generation.

## Phase 1: Azure Infrastructure Setup (30 minutes)

### Prerequisites
1. **Azure Account** with sufficient credits (~$15,000/month budget)
2. **Local Development Environment:**
   - Windows 10/11 with WSL2 or Linux
   - Azure CLI 2.0+
   - Terraform 1.0+
   - Docker Desktop
   - Git
   - Visual Studio Code

### Step 1: Clone and Setup Repository
```bash
# Create project directory
mkdir avatar-ai-production
cd avatar-ai-production

# Initialize git repository
git init

# Create the Terraform files (from the artifacts above)
# Save the terraform files: main.tf, vm.tf
# Save the deployment script: deploy.sh

# Make deployment script executable
chmod +x deploy.sh
```

### Step 2: Install Dependencies
```bash
# Install Azure CLI (if not installed)
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install Terraform (if not installed)
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# Install Docker (if not installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

### Step 3: Deploy Infrastructure
```bash
# Run the complete deployment
./deploy.sh

# This will:
# 1. Login to Azure
# 2. Deploy all infrastructure
# 3. Setup container registry
# 4. Create application structure
```

## Phase 2: Application Setup (45 minutes)

### Step 1: Environment Configuration
```bash
cd avatar-ai-system

# Copy environment template
cp .env.example .env

# Edit .env file with your API keys
nano .env
```

**Required API Keys:**
```env
# OpenAI API Key (Required)
OPENAI_API_KEY=sk-your-openai-key-here

# D-ID API Key (Required for avatar generation)
DID_API_KEY=your-did-api-key-here

# Optional: ElevenLabs for premium voice (fallback to OpenAI TTS)
ELEVENLABS_API_KEY=your-elevenlabs-key-here

# Azure Storage (auto-configured by terraform)
AZURE_STORAGE_CONNECTION_STRING=your-azure-storage-string

# Database (auto-configured by terraform)
DATABASE_URL=postgresql://avataraiuser:AvatarAI2025!@#@your-postgres-host:5432/avatar_ai_db

# Redis (auto-configured by terraform)
REDIS_URL=redis://your-redis-host:6379
```

### Step 2: Create Application Files
Save the following files in the respective directories:

1. **Core AI Services** → `backend/avatar_ai_services.py`
2. **Main Backend** → `backend/main.py`
3. **Frontend Interface** → `frontend_interface.html`
4. **Requirements** → `backend/requirements.txt`

### Step 3: Test Locally
```bash
# Install Python dependencies
cd backend
pip install -r requirements.txt

# Test the services
python avatar_ai_services.py

# Run the backend server
python main.py

# Open browser to http://localhost:8000
```

## Phase 3: Production Deployment (30 minutes)

### Step 1: Build and Deploy Docker Images
```bash
# Get ACR credentials from terraform output
ACR_NAME=$(terraform output -raw container_registry_url | cut -d'.' -f1)

# Build and push backend image
docker build -f infrastructure/docker/Dockerfile.backend -t $ACR_NAME.azurecr.io/avatar-ai-backend:latest .
docker push $ACR_NAME.azurecr.io/avatar-ai-backend:latest

# Deploy to Azure VM Scale Sets (auto-configured)
```

### Step 2: Configure Load Balancer
```bash
# Get load balancer IP
LB_IP=$(terraform output -raw load_balancer_ip)
echo "Your application will be available at: http://$LB_IP"

# Configure your domain (optional)
# Point your domain DNS A record to $LB_IP
```

### Step 3: SSL Configuration (Production)
```bash
# Install Certbot on web VMs
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate (run on each web VM)
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

## Phase 4: Performance Optimization

### Monitoring Setup
```bash
# Install Azure Monitor agent on VMs
# Monitor metrics: CPU, Memory, GPU utilization, Response time

# Set up alerts for:
# - High CPU (>80%)
# - High memory (>90%) 
# - GPU memory (>90%)
# - Response time (>5 seconds)
```

### Auto-Scaling Configuration
- **AI Processing VMs:** Scale 1-10 instances based on CPU/GPU usage
- **Web/API VMs:** Scale 2-20 instances based on connection count
- **Target Metrics:**
  - CPU: 70% average utilization
  - Response time: <3 seconds
  - Concurrent users: 500 per web VM

## Phase 5: Cost Optimization

### Estimated Costs (5,000 DAU)
- **AI Processing (2-4 A100 VMs):** $7,000-14,000/month
- **Web/API Tier (3-6 D16s VMs):** $2,000-4,000/month  
- **Database & Storage:** $500-1,000/month
- **D-ID API (200K API calls):** $4,000/month
- **OpenAI API (1M tokens/day):** $600/month
- **Total:** $14,000-24,000/month

### Cost Reduction Strategies
1. **Reserved Instances:** 30% savings on compute
2. **Spot Instances:** 70% savings for non-critical workloads
3. **Custom Avatar Pipeline:** Replace D-ID after MVP validation
4. **Edge Caching:** CDN for avatar videos
5. **Compression:** Optimize video/audio formats

## Production Readiness Checklist

### Security
- [ ] API rate limiting (100 requests/minute per user)
- [ ] Input validation and sanitization
- [ ] HTTPS with valid SSL certificates
- [ ] WAF (Web Application Firewall) enabled
- [ ] API key rotation schedule
- [ ] User authentication (JWT tokens)

### Performance
- [ ] CDN configuration for static assets
- [ ] Database query optimization
- [ ] Redis caching strategy
- [ ] Video compression settings
- [ ] Load testing completed (10K concurrent users)

### Monitoring
- [ ] Application Performance Monitoring (APM)
- [ ] Error tracking and alerting
- [ ] Business metrics dashboard
- [ ] Capacity planning reports
- [ ] User experience monitoring

### Backup & Recovery
- [ ] Database backup automation
- [ ] Configuration backup
- [ ] Disaster recovery plan
- [ ] Data retention policies
- [ ] GDPR compliance measures

## API Usage Examples

### WebSocket Connection
```javascript
const ws = new WebSocket('wss://yourdomain.com/ws/user123');

// Send text message
ws.send(JSON.stringify({
    type: 'text_input',
    text: 'Hello, how are you?',
    voice: 'alloy',
    avatar_type: 'female'
}));

// Send audio message
ws.send(JSON.stringify({
    type: 'audio_input',
    audio_data: base64AudioData,
    voice: 'nova',
    avatar_type: 'male'
}));
```

### REST API Testing
```bash
# Health check
curl https://yourdomain.com/health

# Test text processing
curl -X POST https://yourdomain.com/api/test-text \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "user_id": "test"}'

# Get system stats
curl https://yourdomain.com/stats
```

## Scaling Beyond 10K Users

### Horizontal Scaling (50K+ users)
1. **Multi-Region Deployment:** Deploy in 3+ Azure regions
2. **Database Sharding:** Partition users across databases
3. **Message Queuing:** Redis Streams or Azure Service Bus
4. **Microservices:** Split services into separate containers

### Advanced Features
1. **Custom Avatar Training:** Train personalized avatars per user
2. **Real-time Lip Sync:** Replace D-ID with custom solution
3. **Voice Cloning:** Personalized TTS voices
4. **Multi-language Support:** 20+ languages
5. **Mobile Apps:** iOS/Android native applications

## Support and Maintenance

### Regular Tasks
- **Daily:** Monitor system health, check error logs
- **Weekly:** Review performance metrics, cost analysis
- **Monthly:** Security updates, capacity planning
- **Quarterly:** Technology updates, feature releases

### Emergency Procedures
1. **High Error Rate:** Scale up AI processing VMs
2. **Service Outage:** Failover to secondary region
3. **Cost Spike:** Implement emergency rate limiting
4. **Security Incident:** Rotate API keys, review access logs

---

## Next Steps After Deployment

1. **Week 1:** Monitor performance, fix any issues
2. **Week 2:** Implement user feedback, optimize performance  
3. **Month 1:** Add advanced features (voice selection, avatar customization)
4. **Month 2:** Begin custom avatar pipeline development
5. **Month 3:** Launch premium tier with custom avatars

This architecture will handle 10K+ users with room to scale to 100K+ users with minimal changes. The hybrid D-ID + custom approach gives you immediate market entry while building competitive advantages for the long term.
