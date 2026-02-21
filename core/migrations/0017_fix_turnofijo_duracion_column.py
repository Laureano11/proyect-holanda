from django.db import migrations


def add_duracion_minutos_column(apps, schema_editor):
    TurnoFijo = apps.get_model('core', 'TurnoFijo')
    table_name = TurnoFijo._meta.db_table
    try:
        columns = [col.name for col in schema_editor.connection.introspection.get_table_description(schema_editor.connection.cursor(), table_name)]
    except Exception:
        columns = []
    if 'duracion_minutos' not in columns:
        table_sql = schema_editor.quote_name(table_name)
        column_sql = schema_editor.quote_name('duracion_minutos')
        schema_editor.execute(f"ALTER TABLE {table_sql} ADD COLUMN {column_sql} integer")


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_turnofijo_duracion_minutos'),
    ]

    operations = [
        migrations.RunPython(add_duracion_minutos_column, migrations.RunPython.noop),
    ]
