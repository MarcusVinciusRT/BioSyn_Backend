-- ============================================================
-- Restaura o acesso de leitura do backend ao lakehouse.
--
-- RODE COMO ADMIN (nao como APP_BACKEND).
-- SQL Developer, SQLcl ou Database Actions no console da OCI.
--
-- Contexto: em 2026-09-08 o backend perdeu o SELECT em GOLD.INTERNACOES.
-- Sem ele, POST /relatorios responde 502 FALHA_LAKEHOUSE e o Select AI nao
-- consegue ler a tabela do object_list do APP_PROFILE.
-- ============================================================

-- 1) O grant que o backend precisa. Somente leitura -- nao conceda mais que isso.
GRANT SELECT ON GOLD.INTERNACOES TO APP_BACKEND;

-- 2) Conferencia: deve devolver uma linha (GOLD / INTERNACOES / SELECT).
SELECT grantee, owner, table_name, privilege
  FROM dba_tab_privs
 WHERE grantee = 'APP_BACKEND'
   AND owner   = 'GOLD';

-- 3) Se o passo 2 vier vazio, a tabela pode ter sido recriada com outro nome.
--    Esta consulta mostra o que existe no schema GOLD:
SELECT object_name, object_type, created
  FROM dba_objects
 WHERE owner = 'GOLD'
 ORDER BY object_name;

-- ============================================================
-- Depois de rodar, o proprio backend confirma:
--   .venv/bin/python -m pytest tests/ -q -m banco
-- ============================================================
