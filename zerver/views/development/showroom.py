import os

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

background_colors = [
    {"name": gettext_lazy("Default background"), "css_var": "--color-background"},
    {"name": gettext_lazy("Popover background"), "css_var": "--color-background-popover-menu"},
    {"name": gettext_lazy("Modal background"), "css_var": "--color-background-modal"},
    {"name": gettext_lazy("Compose background"), "css_var": "--color-compose-box-background"},
]


def get_svg_filenames() -> list[str]:
    icons_dir = os.path.join(os.path.dirname(__file__), "../../../web/icons")

    # Get all .svg file names from the directory
    svg_files = [f for f in os.listdir(icons_dir) if f.endswith(".svg")]

    # Remove the .svg extension from the file names
    icon_names = [os.path.splitext(f)[0] for f in svg_files]

    # Sort the list alphabetically
    return sorted(icon_names)


def showroom_component_buttons(request: HttpRequest) -> HttpResponse:
    context = {
        "background_colors": background_colors,
        "icons": get_svg_filenames(),
        "page_is_showroom": True,
        "showroom_component": "buttons",
        "doc_root_title": _("Button styles browser"),
        # We set isolated_page to avoid clutter from footer/header.
        "isolated_page": True,
    }
    return render(request, "zerver/development/showroom/buttons.html", context)


def showroom_component_banners(request: HttpRequest) -> HttpResponse:
    context = {
        "background_colors": background_colors,
        "icons": get_svg_filenames(),
        "page_is_showroom": True,
        "showroom_component": "banners",
        "doc_root_title": _("Banner styles browser"),
        # We set isolated_page to avoid clutter from footer/header.
        "isolated_page": True,
    }
    return render(request, "zerver/development/showroom/banners.html", context)


def showroom_component_inputs(request: HttpRequest) -> HttpResponse:
    context = {
        "background_colors": background_colors,
        "icons": get_svg_filenames(),
        "page_is_showroom": True,
        "showroom_component": "inputs",
        "doc_root_title": _("Input styles browser"),
        # We set isolated_page to avoid clutter from footer/header.
        "isolated_page": True,
    }
    return render(request, "zerver/development/showroom/inputs.html", context)
