-- Тестовый кабинет: логин admin, пароль admin. Почта внутренняя, писем нет.
-- Пользователь вставляется напрямую: API Auth не принимает пароль короче 6 символов.
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
) values (
  '00000000-0000-0000-0000-000000000000', 'a0000000-0000-4000-8000-000000000001', 'authenticated', 'authenticated',
  'admin@leadbombing.local', extensions.crypt('admin', extensions.gen_salt('bf')), now(),
  '{"provider": "email", "providers": ["email"]}', '{"login": "admin"}', now(), now(),
  '', '', '', ''
);

insert into auth.identities (id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at)
values (
  gen_random_uuid(), 'a0000000-0000-4000-8000-000000000001', 'a0000000-0000-4000-8000-000000000001',
  '{"sub": "a0000000-0000-4000-8000-000000000001", "email": "admin@leadbombing.local", "email_verified": true}',
  'email', now(), now(), now()
);
