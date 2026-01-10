-- 创建兑换码表
CREATE TABLE IF NOT EXISTS public.redeem_codes (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    code VARCHAR(20) NOT NULL UNIQUE,
    target_name VARCHAR(100) NOT NULL,
    cat_coins INTEGER DEFAULT 0,
    credits INTEGER NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    note TEXT DEFAULT '',
    is_used BOOLEAN DEFAULT FALSE,
    used_by UUID REFERENCES public.profiles(id),
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_redeem_codes_code ON public.redeem_codes(code);
CREATE INDEX IF NOT EXISTS idx_redeem_codes_is_used ON public.redeem_codes(is_used);
CREATE INDEX IF NOT EXISTS idx_redeem_codes_created_at ON public.redeem_codes(created_at DESC);

-- 启用 RLS
ALTER TABLE public.redeem_codes ENABLE ROW LEVEL SECURITY;

-- 创建策略：允许所有操作（通过 service_role key）
CREATE POLICY "Allow all operations for service role" ON public.redeem_codes
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- 添加注释
COMMENT ON TABLE public.redeem_codes IS '兑换码表 - 用于生成和管理积分兑换码';
COMMENT ON COLUMN public.redeem_codes.code IS '兑换码（唯一）';
COMMENT ON COLUMN public.redeem_codes.target_name IS '目标用户姓名';
COMMENT ON COLUMN public.redeem_codes.cat_coins IS '猫币数量（0表示商学院用户）';
COMMENT ON COLUMN public.redeem_codes.credits IS '积分数量';
COMMENT ON COLUMN public.redeem_codes.created_by IS '创建人（管理员）';
COMMENT ON COLUMN public.redeem_codes.note IS '备注';
COMMENT ON COLUMN public.redeem_codes.is_used IS '是否已使用';
COMMENT ON COLUMN public.redeem_codes.used_by IS '使用者用户ID';
COMMENT ON COLUMN public.redeem_codes.used_at IS '使用时间';
