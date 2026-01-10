-- 创建管理员操作日志表
CREATE TABLE IF NOT EXISTS admin_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    admin_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_name VARCHAR(100),
    target VARCHAR(255),
    details TEXT,
    extra_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引以加速查询
CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON admin_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_logs_action_type ON admin_logs(action_type);
CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_name ON admin_logs(admin_name);

-- 添加注释
COMMENT ON TABLE admin_logs IS '管理员操作日志表';
COMMENT ON COLUMN admin_logs.admin_name IS '管理员名称';
COMMENT ON COLUMN admin_logs.action_type IS '操作类型：PROMPT_CREATE, PROMPT_UPDATE, REDEEM_CREATE 等';
COMMENT ON COLUMN admin_logs.action_name IS '操作名称（中文）';
COMMENT ON COLUMN admin_logs.target IS '操作目标（模块名、用户名等）';
COMMENT ON COLUMN admin_logs.details IS '详细描述';
COMMENT ON COLUMN admin_logs.extra_data IS '额外数据（JSON格式）';

-- 禁用 RLS（允许服务端访问）
ALTER TABLE admin_logs ENABLE ROW LEVEL SECURITY;

-- 创建策略：允许服务端完全访问
CREATE POLICY "Service role can do everything" ON admin_logs
    FOR ALL
    USING (true)
    WITH CHECK (true);
