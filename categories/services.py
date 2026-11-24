def lock_hierarchy(connection):
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(476137880839292601)")
