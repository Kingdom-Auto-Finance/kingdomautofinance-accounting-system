-- Migration: Initial tables for FastAPI backend
-- Description: Creates users, audit_log, and jobs tables
-- Date: 2026-01-08

-- User management table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'readonly')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true
);

-- Create index on email for fast lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id VARCHAR(255),
    details JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for audit log queries
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log(entity_type, entity_id);

-- Job queue status table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    progress JSONB DEFAULT '{"current": 0, "total": 0, "message": ""}'::jsonb,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Create indexes for job queries
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_type_status ON jobs(job_type, status);

-- Add indexes for performance on existing tables (if they don't exist)
CREATE INDEX IF NOT EXISTS idx_payments_log_loan_date ON payments_log(loan_id, payment_date);
CREATE INDEX IF NOT EXISTS idx_payments_log_processed ON payments_log(processed) WHERE processed = false;
CREATE INDEX IF NOT EXISTS idx_payments_log_id ON payments_log(id);

-- Create a default admin user (password: Kingdom2025!$$)
-- Password hash generated with bcrypt for 'Kingdom2025!$$'
-- You should change this after first login!
INSERT INTO users (email, password_hash, full_name, role, is_active)
VALUES (
    'admin@kingdomautofinance.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5yrq5rWlzmzVi',  -- Kingdom2025!$$
    'System Administrator',
    'admin',
    true
)
ON CONFLICT (email) DO NOTHING;

-- Add comment to remind about password change
COMMENT ON TABLE users IS 'User management table. Default admin password is Kingdom2025!$$ - CHANGE IMMEDIATELY after setup!';
