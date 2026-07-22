# -*- coding: utf-8 -*-
#⬇️ Imports (optional)
from pyrevit import script

#📦 Variables (optional)
output = script.get_output()


#⚙️ Example Function
def default_print(btn_name):
    """This is a simple print placeholder function that can be reused in all scripts."""

    # 👀 Print Message
    output.print_md('# ✨ You Clicked Button \'{btn_name}\' ✨'.format(btn_name=btn_name))  # <- Print MarkDown Heading 2
    output.print_md('---')
    output.print_md('⌨️ Hold **ALT + CLICK** to open the source code of this button. ')
    output.print_md('You can Duplicate, or use this placeholder for your own script.')
    output.print_md('---')
    output.print_md('*pyRevit StarterKit 2.0 was made by Erik Frits from LearnRevitAPI.com*')
    output.print_md('**Happy Coding!**')

#███████████████████████████████████████████████████████████████████████████
# How it works?
# 1. Create python file in lib or lib/your-nested-folder (e.g. lib/_example.py or lib/reusable_code/_example.py)
# 2. Ensure __init__.py file exists in all nested lib folders (it can be empty)
# 3. Write reusable code (function, classes, variables...)
# 4. Import in your regular tools (e.g. from _example.py import * or from reusable_code._example import *)
# 5. Done. Now Reuse Code Like a Pro!

# For more info, check out this tutorial:
free_tutorial = 'https://www.LearnRevitAPI.com/resources/pyrevit-lib'