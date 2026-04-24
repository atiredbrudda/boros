# Dummy research page — cite fails

This page has no wiki-link references in prose. It only has one inside a code block:

```python
# Example showing how to reference [[Some-page]] inside code — doesn't count
link = "[[wiki-link-inside-code]]"
```

No valid citation outside code blocks — lint must fail.
