-- 给 profiles 表添加手机号字段
-- 执行方式：在 Supabase Dashboard -> SQL Editor 中运行

-- 1. 添加 phone 列
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS phone VARCHAR(20);

-- 2. 创建唯一索引（手机号非空时唯一）
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_phone_unique
  ON public.profiles(phone)
  WHERE phone IS NOT NULL AND phone != '';

-- 3. 添加注释
COMMENT ON COLUMN public.profiles.phone IS '用户手机号（选填，唯一）';
