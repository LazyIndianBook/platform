"""The admin theme on the redesign's tokens (docs/design/direction.md): the save button and the links' hover take
--accent #1A6E30 (white text 6.3:1; #2F8F3A gave 4.1:1, under 4.5), the hovers are 6 % darker as on the site, the title
is white on the navy header, the selected module row takes --secondary."""

from django.db import migrations

NAVY, ACCENT, ACCENT_HOVER, PAPER_ALT, RED_HOVER = "#0B2A5B", "#1A6E30", "#18672D", "#F4EFE3", "#A92117"


def tokens(apps, schema_editor):
    from admin_interface.cache import del_cached_active_theme

    apps.get_model("admin_interface", "Theme").objects.filter(name="ExamLeaf").update(
        title_color="#FFFFFF",
        css_module_background_selected_color=PAPER_ALT,
        css_module_link_selected_color=NAVY,
        css_generic_link_color=NAVY,
        css_generic_link_hover_color=ACCENT,
        css_generic_link_active_color=ACCENT,
        css_save_button_background_color=ACCENT,
        css_save_button_background_hover_color=ACCENT_HOVER,
        css_save_button_text_color="#FFFFFF",
        css_delete_button_background_hover_color=RED_HOVER,
    )
    del_cached_active_theme()


class Migration(migrations.Migration):
    dependencies = [("ops", "0003_email_suppression")]
    operations = [migrations.RunPython(tokens, migrations.RunPython.noop)]
