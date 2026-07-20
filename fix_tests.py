import sys

with open('tests/test_all.py', 'r') as f:
    content = f.read()

content = content.replace('"Design a box"', '"Box Design"')
content = content.replace('"Find a driver"', '"Bass Match"')

with open('tests/test_all.py', 'w') as f:
    f.write(content)
