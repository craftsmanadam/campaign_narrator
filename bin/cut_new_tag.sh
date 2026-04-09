TAG_NAME="$(poetry version --short)"
git tag -s "$TAG_NAME" -m "$TAG_NAME"
git push origin tag $TAG_NAME
