-- Eliminar el registro de la migración de merge que ya no existe
DELETE FROM django_migrations 
WHERE app = 'core' AND name = '0007_merge_20251228_1114';

-- Verificar las migraciones restantes de core
SELECT * FROM django_migrations WHERE app = 'core' ORDER BY id;

