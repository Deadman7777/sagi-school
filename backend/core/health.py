from django.db import connection
from django.http import JsonResponse


def health(request):
    try:
        connection.ensure_connection()
    except Exception as e:
        return JsonResponse({'status': 'error', 'db': str(e)}, status=503)
    return JsonResponse({'status': 'ok'})
