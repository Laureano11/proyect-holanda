#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # region agent log: pre-migrate-argv-check (hypothesis H1/H2/H3)
    try:
        with open("/home/lauri11/Documentos/proyect-holanda/.cursor/debug.log", "a", encoding="utf-8") as _debug_f:
            import json as _json
            _debug_f.write(
                _json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H1",
                        "location": "manage.py:main",
                        "message": "manage.py invoked",
                        "data": {"argv": sys.argv},
                        "timestamp": __import__("time").time(),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion

    if any(arg == "migrate" for arg in sys.argv):
        try:
            import django
            from django.db import connections
            from django.db.migrations.loader import MigrationLoader

            django.setup()
            connection = connections["default"]
            loader = MigrationLoader(connection)
            leaf_nodes = loader.graph.leaf_nodes()
            root_nodes = loader.graph.root_nodes()

            # region agent log: leaf-nodes (hypothesis H1/H2/H3)
            try:
                with open("/home/lauri11/Documentos/proyect-holanda/.cursor/debug.log", "a", encoding="utf-8") as _debug_f:
                    import json as _json
                    _debug_f.write(
                        _json.dumps(
                            {
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "H1",
                                "location": "manage.py:migrate_leaf_nodes",
                                "message": "Migration leaf nodes detected",
                                "data": {"leaf_nodes": leaf_nodes},
                                "timestamp": __import__("time").time(),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion

            # region agent log: root-nodes (hypothesis H3)
            try:
                with open("/home/lauri11/Documentos/proyect-holanda/.cursor/debug.log", "a", encoding="utf-8") as _debug_f:
                    import json as _json
                    _debug_f.write(
                        _json.dumps(
                            {
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "H3",
                                "location": "manage.py:migrate_root_nodes",
                                "message": "Migration root nodes detected",
                                "data": {"root_nodes": root_nodes, "node_count": len(loader.graph.nodes)},
                                "timestamp": __import__("time").time(),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
        except Exception as migrate_debug_exc:
            # region agent log: migrate-debug-exc (hypothesis H2/H3)
            try:
                with open("/home/lauri11/Documentos/proyect-holanda/.cursor/debug.log", "a", encoding="utf-8") as _debug_f:
                    import json as _json
                    _debug_f.write(
                        _json.dumps(
                            {
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "H2",
                                "location": "manage.py:migrate_leaf_nodes",
                                "message": "Failed to inspect migration graph",
                                "data": {"error": str(migrate_debug_exc)},
                                "timestamp": __import__("time").time(),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

