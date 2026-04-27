import json

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .services import RoutePlanningError, plan_route


def health_check(request):
    return JsonResponse({"status": "ok"})


@method_decorator(csrf_exempt, name="dispatch")
class RoutePlanView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Request body must be valid JSON."}, status=400)

        start = payload.get("start")
        finish = payload.get("finish")
        if not start or not finish:
            return JsonResponse(
                {"error": "Both 'start' and 'finish' are required."},
                status=400,
            )

        try:
            result = plan_route(start=start, finish=finish)
        except RoutePlanningError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception:
            return JsonResponse(
                {"error": "Unable to plan route right now."},
                status=502,
            )

        return JsonResponse(result, json_dumps_params={"indent": 2})
