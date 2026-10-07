"""The admin theme (django-admin-interface): ExamLeaf's name and colours. The related-object pop-up stays a window
(related_modal_active off), because the modal is an iframe and the site forbids framing (CSP frame-ancestors 'none')."""

from django.db import migrations

NAVY, LEAF, LIGHT_LEAF, RED = "#0B2A5B", "#2F8F3A", "#8FD694", "#B42318"


def brand(apps, schema_editor):
    from admin_interface.cache import del_cached_active_theme

    Theme = apps.get_model("admin_interface", "Theme")
    Theme.objects.update(active=False)
    Theme.objects.update_or_create(
        name="ExamLeaf",
        defaults=dict(
            active=True,
            title="ExamLeaf admin",
            title_visible=True,
            logo_visible=False,
            related_modal_active=False,
            language_chooser_active=False,  # English only (and the chooser needs LocaleMiddleware)
            css_header_background_color=NAVY,
            css_header_text_color="#FFFFFF",
            css_header_link_color="#FFFFFF",
            css_header_link_hover_color=LIGHT_LEAF,
            css_module_background_color=NAVY,
            css_module_text_color="#FFFFFF",
            css_module_link_color="#FFFFFF",
            css_module_link_hover_color=LIGHT_LEAF,
            css_module_background_selected_color="#E8F3EA",
            css_module_link_selected_color=NAVY,
            css_generic_link_color=NAVY,
            css_generic_link_hover_color=LEAF,
            css_generic_link_active_color=LEAF,
            css_save_button_background_color=LEAF,
            css_save_button_background_hover_color="#1F6B28",
            css_save_button_text_color="#FFFFFF",
            css_delete_button_background_color=RED,
            css_delete_button_background_hover_color="#8A1A12",
            css_delete_button_text_color="#FFFFFF",
        ),
    )
    del_cached_active_theme()


class Migration(migrations.Migration):
    dependencies = [("admin_interface", "0032_alter_theme_defaults")]
    operations = [migrations.RunPython(brand, migrations.RunPython.noop)]
