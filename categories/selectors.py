from collections import defaultdict, deque

from django.db import connection
from django.db.models.expressions import RawSQL

from .models import Category


def visible_category_ids(root=None):
    if connection.vendor == 'postgresql':
        # Walk only active branches. The optional seed must itself be publicly visible.
        sql = """
            WITH RECURSIVE visible(id) AS (
                SELECT id FROM categories_category WHERE is_active AND parent_id IS NULL
                UNION ALL
                SELECT category.id FROM categories_category category
                JOIN visible ON category.parent_id = visible.id WHERE category.is_active
            )
        """
        if root is None:
            return RawSQL(sql + "SELECT id FROM visible", ())
        return RawSQL(sql + """
            , subtree(id) AS (
                SELECT id FROM visible WHERE id = %s
                UNION ALL
                SELECT category.id FROM categories_category category
                JOIN subtree ON category.parent_id = subtree.id WHERE category.is_active
            )
            SELECT id FROM subtree
        """, (root,))
    children = defaultdict(list)
    for pk, parent in Category.objects.filter(is_active=True).values_list('pk', 'parent_id'):
        children[parent].append(pk)
    queue = deque(children[None])
    visible = set()
    while queue:
        pk = queue.popleft()
        if pk not in visible:
            visible.add(pk)
            queue.extend(children[pk])
    if root is None:
        return visible
    if root not in visible:
        return set()
    queue = deque([root])
    subtree = set()
    while queue:
        pk = queue.popleft()
        subtree.add(pk)
        queue.extend(children[pk])
    return subtree


def public_categories():
    return Category.objects.filter(pk__in=visible_category_ids()).order_by('name', 'pk')
