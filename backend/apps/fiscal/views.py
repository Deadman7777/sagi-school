from rest_framework.response import Response
from rest_framework.views import APIView

class PlaceholderView(APIView):
    def get(self, request):
        return Response({'module': 'fiscal', 'status': 'en développement'})
