import redis
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from actions.utils import create_action
from common.decorators import ajax_required

from .forms import ImageCreateForm
from .models import Image

r = redis.Redis(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT, db=settings.REDIS_DB
)


@login_required
def image_create(request):
    if request.method == "POST":
        form = ImageCreateForm(data=request.POST)
        if form.is_valid():
            new_item = form.save(commit=False)
            new_item.user = request.user
            new_item.save()
            create_action(request.user, "bookmarked image", new_item)
            messages.success(request, "Image added successfully")
            return redirect(new_item.get_absolute_url())
    else:
        form = ImageCreateForm(data=request.GET)
    return render(
        request, "images/image/create.html", {"section": "images", "form": form}
    )


def image_detail(request, id, slug):
    image = get_object_or_404(Image, id=id, slug=slug)

    total_views = r.incr(
        f"image:{image.id}:views"
    )  # Increment the total image views by 1

    r.zincrby(
        "image_ranking", 1, image.id
    )  # Increment the image ranking by 1 in the sorted set 'image_ranking'

    return render(
        request,
        "images/image/detail.html",
        {"section": "images", "image": image, "total_views": total_views},
    )


@ajax_required
@login_required
@require_POST
def image_like(request):
    image_id = request.POST.get("id")
    action = request.POST.get("action")
    if image_id and action:
        try:
            image = Image.objects.get(id=image_id)
            if action == "like":
                image.users_like.add(request.user)
                create_action(request.user, "likes", image)
            else:
                image.users_like.remove(request.user)
            return JsonResponse({"status": "ok"})
        except Image.DoesNotExist:
            return JsonResponse({"status": "error"})
    return JsonResponse({"status": "error"})


@login_required
def image_list(request):
    images = Image.objects.all()
    paginator = Paginator(images, 8)
    page = request.GET.get("page")

    try:
        images = paginator.page(page)
    except PageNotAnInteger:
        images = paginator.page(1)
    except EmptyPage:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return HttpResponse("")
        images = paginator.page(paginator.num_pages)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return render(request, "images/image/list_ajax.html", {"images": images})

    return render(request, "images/image/list.html", {"images": images})


@login_required
def image_ranking(request):
    # Get image ranking dictionary sorted by views (descending)
    image_ranking = r.zrange("image_ranking", 0, -1, desc=True)[:10]

    # Get the IDs of the most viewed images
    image_ranking_ids = [int(id) for id in image_ranking]

    # Get the most viewed Image objects for the retrieved IDs
    most_viewed = list(Image.objects.filter(id__in=image_ranking_ids))

    # Sort the images by their ranking order
    most_viewed.sort(key=lambda x: image_ranking_ids.index(x.id))

    return render(
        request,
        "images/image/ranking.html",
        {"section": "images", "most_viewed": most_viewed},
    )
