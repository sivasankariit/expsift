from django import template


register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_expt_unique_props(form):
    return getattr(form, 'unique_properties', [])
