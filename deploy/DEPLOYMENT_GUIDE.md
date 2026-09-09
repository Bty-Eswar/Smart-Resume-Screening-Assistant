# Complete AWS EC2 Free Tier ($0/mo) Deployment Guide

This guide walks you through deploying the **Smart Resume Screening Assistant ("Shortlist")** onto an **AWS EC2 Free Tier** instance running **Ubuntu 22.04 LTS**, backed by **PostgreSQL** and the **Groq Free-Tier API** (`llama-3.3-70b-versatile`).

---

## 0. Total Cost Breakdown

| Component | Service / Provider | Free Tier Allowance | Monthly Cost |
| :--- | :--- | :--- | :--- |
| **Compute** | AWS EC2 `t2.micro` or `t3.micro` | 750 hours/month (12 Months Free) | **$0.00** |
| **Storage** | AWS EBS gp3 Volume | 30 GB SSD (12 Months Free) | **$0.00** |
| **Bandwidth** | AWS Data Transfer Out | 100 GB/month Free | **$0.00** |
| **Database** | PostgreSQL 16 (in Docker) | Included within EC2 EBS volume | **$0.00** |
| **LLM Inference** | Groq Cloud (`llama-3.3-70b-versatile`) | Free Tier (30 req/min, 14,400 req/day) | **$0.00** |
| **Total** | | | **$0.00 / month** |

---

## 1. Launching Your AWS EC2 Free-Tier Instance

1. Log into your [AWS Management Console](https://console.aws.amazon.com/ec2/).
2. In the top-right corner, select your preferred region (e.g., `us-east-1`, `ap-south-1`, or `eu-west-1`).
3. Click **Launch Instances**:
   - **Name**: `shortlist-production`
   - **Application and OS Images**: Choose **Ubuntu** -> **Ubuntu Server 22.04 LTS (HVM), SSD Volume Type** (Make sure it says *"Free tier eligible"*).
   - **Instance Type**: Select **`t2.micro`** (1 vCPU, 1 GiB Memory) or **`t3.micro`** (if in an eligible region).
   - **Key Pair (login)**: Choose an existing `.pem` key pair or click **Create new key pair** (e.g. `shortlist-key.pem`). Download and save it safely.
   - **Network Settings**:
     - Check **Allow SSH traffic from anywhere** (or your specific IP).
     - Check **Allow HTTP traffic from the internet** (Port 80).
     - Check **Allow HTTPS traffic from the internet** (Port 443).
   - **Configure Storage**:
     - Set volume size to **20 GB** or **30 GB** `gp3` (up to 30 GB is 100% Free Tier eligible).
4. Click **Launch Instance**.
5. Once the instance state shows **Running**, copy the **Public IPv4 address** (e.g., `54.210.35.120`).

---

## 2. Connecting to Your EC2 Instance via SSH

Open your local terminal (PowerShell, Command Prompt, or Git Bash) and run:

```bash
# Set proper permissions on your private key (Linux/macOS)
chmod 400 shortlist-key.pem

# SSH into the Ubuntu EC2 instance
ssh -i shortlist-key.pem ubuntu@<YOUR-EC2-PUBLIC-IP>
```

*(On Windows PowerShell, `ssh -i shortlist-key.pem ubuntu@<YOUR-EC2-PUBLIC-IP>` works directly).*

---

## 3. Automated One-Command Deployment

Once connected to your EC2 instance, clone your repository and run the setup script:

```bash
# 1. Clone your project repository
git clone https://github.com/Bty-Eswar/Smart-Resume-Screening-Assistant.git
cd Smart-Resume-Screening-Assistant

# 2. Make the setup script executable and run it with sudo
chmod +x deploy/setup_ec2.sh
sudo ./deploy/setup_ec2.sh
```

### What `setup_ec2.sh` does automatically:
1. **Configures 2GB Swap Memory**: Crucial for EC2 `t2.micro` (1GB RAM) to ensure image compilation (`npm run build`, Python wheels) runs smoothly without triggering Out-Of-Memory errors.
2. **Installs Docker & Docker Compose**: Configures official Docker apt repositories and installs the latest Docker engine.
3. **Configures Firewall (UFW)**: Enables ports 22 (SSH), 80 (HTTP), and 443 (HTTPS).
4. **Sets Up Environment (`.env`)**: Prompts for your Groq API key (`gsk_...`) if not already present.
5. **Launches the Entire Stack with Docker Compose**:
   - **PostgreSQL 16** (`shortlist-postgres`) with persistent data volume.
   - **FastAPI Backend** (`shortlist-backend`) listening on internal port 8000.
   - **Nginx Web Server + React SPA** (`shortlist-frontend`) serving the web UI and reverse-proxying API traffic on port 80.

---

## 4. Accessing Your Live Web Application

Once the script completes, open your browser and navigate to:

```text
http://<YOUR-EC2-PUBLIC-IP>/
```

You will see the **Shortlist** dashboard live on the internet!
- You can create new jobs with job descriptions.
- Edit and confirm criteria weights.
- Upload candidate PDFs or click **"Use sample resumes"**.
- Run all 3 ranking methods (**R0 Lexical**, **R1 Semantic Dense Embedding**, **R2 Groq Llama 3.3 70B**) or compare them side-by-side in the **Tri-Model Consensus Matrix**.
- View exact character-offset verbatim citations in the evidence drawer.
- Change candidate verdicts (**Accept** / **Reject**) which are persistently stored in **PostgreSQL**.

---

## 5. PostgreSQL Database Management

### Inspecting Data Inside PostgreSQL:
```bash
# Connect to the PostgreSQL database container via psql
docker exec -it shortlist-postgres psql -U shortlist -d shortlist_db

# Useful SQL queries:
\dt                          -- List all tables (jobs, rankings, verdicts)
SELECT job_id, title, status, created_at FROM jobs;
SELECT job_id, ranker_id, created_at FROM rankings;
SELECT * FROM verdicts;
\q                          -- Exit psql
```

### (Optional) Connecting to Free Cloud PostgreSQL (Supabase or Neon):
If you prefer using a serverless managed PostgreSQL (which also has a 100% Free Tier):
1. Create a free database on [Neon.tech](https://neon.tech) or [Supabase.com](https://supabase.com).
2. Copy your connection string: `postgresql://user:password@ep-cool-project.us-east-2.aws.neon.tech/neondb?sslmode=require`.
3. In your EC2 `.env` file, add:
   ```env
   DATABASE_URL=postgresql://user:password@ep-cool-project.us-east-2.aws.neon.tech/neondb?sslmode=require
   GROQ_API_KEY=gsk_...
   ```
4. Restart backend: `docker compose restart backend`.
5. The application will automatically use your cloud PostgreSQL instance!

---

## 6. Daily Management & Maintenance Commands

```bash
# View live logs of all services
docker compose logs -f

# View live backend logs only
docker compose logs -f backend

# Check container health and memory usage
docker compose ps
docker stats

# Restart services after updating code
git pull
docker compose up -d --build

# Stop all containers
docker compose down
```
