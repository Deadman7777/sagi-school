from django.utils.functional import SimpleLazyObject
from .tenant import _resolve_tenant


class TenantMiddleware:
    """
    Attache request.tenant en lazy : la résolution sécurisée
    (cf. core/tenant.py) se fait au premier accès, dans la vue,
    après que DRF/JWT a authentifié request.user.

    Le header X-Tenant-ID est seulement parsé ici (pas de lookup DB) ;
    il n'est utilisé que si l'user authentifié est SUPER_ADMIN.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        header = request.headers.get('X-Tenant-ID')
        if header and header not in ('null', ''):
            request._tenant_id_from_header = header
        else:
            request._tenant_id_from_header = None

        # Résolution lazy : exécutée à la lecture de request.tenant
        request.tenant = SimpleLazyObject(lambda: _resolve_tenant(request))

        return self.get_response(request)


class ApiSansCacheMiddleware:
    """Une réponse d'API n'est jamais resservie depuis un cache.

    Ni Django ni nginx ne posaient d'en-tête sur /api/ : sans consigne, le
    navigateur — et Electron, qui a le même cache HTTP — est libre de rendre
    l'ancienne réponse. On modifiait une échéance dans Paramètres, on passait
    dans un autre module, on revenait : la valeur d'avant était de retour.
    Elle n'était pas perdue, elle était relue dans le cache.

    Le rechargement forcé (Ctrl+Shift+R) masquait le problème sur le cloud,
    et n'existe même pas sur un poste local.

    Une vue qui pose délibérément son propre Cache-Control garde le sien.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith('/api/') and not response.has_header('Cache-Control'):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response


class DroitsEcritureMiddleware:
    """Le serveur refuse les écritures qu'un rôle ne voit pas dans son menu.

    Les rôles (Responsable RH, comptable, scolarité, Lecteur) n'étaient
    appliqués qu'à l'affichage du menu — et au seul module RH côté serveur. Un
    compte « Lecteur » pouvait donc, en appelant l'API directement, enregistrer
    ou annuler des paiements, supprimer des charges.

    Contrôle central plutôt que vue par vue : une vue ajoutée demain est
    couverte d'office. Seules les ÉCRITURES (POST, PUT, PATCH, DELETE) sont
    filtrées — les écrans lisent légitimement d'autres modules pour leurs
    listes déroulantes. Le jeton est lu ici parce que DRF n'authentifie
    qu'à l'intérieur de la vue.
    """
    METHODES_LECTURE = ('GET', 'HEAD', 'OPTIONS')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        refus = self._refus(request)
        return refus if refus is not None else self.get_response(request)

    def _refus(self, request):
        if request.method in self.METHODES_LECTURE or not request.path.startswith('/api/'):
            return None
        from .permissions import MODULES_ECRITURE, peut_ecrire
        prefixe = request.path.split('/')[2] if request.path.count('/') >= 3 else ''
        if prefixe not in MODULES_ECRITURE:
            return None
        from rest_framework_simplejwt.authentication import JWTAuthentication
        try:
            resultat = JWTAuthentication().authenticate(request)
        except Exception:
            return None          # jeton invalide : DRF répondra 401 dans la vue
        if resultat is None:
            return None
        user = resultat[0]
        if peut_ecrire(user, prefixe):
            return None
        from django.http import JsonResponse
        return JsonResponse(
            {'error': "Votre rôle ne permet pas de modifier ces données. "
                      "Demandez à l'administrateur de l'établissement."},
            status=403)
