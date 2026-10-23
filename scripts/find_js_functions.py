import os
import re


def find_all_js_functions(root_dir):
    # Pattern to extract content between <script> tags
    script_block_pattern = re.compile(
        r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE
    )

    # Combined Pattern for:
    # 1. Traditional & Async functions: function foo() or async function foo()
    # 2. Arrows & Assignments: const foo = () => or let foo = function()
    function_pattern = re.compile(
        r"(?:(?:async\s+)?function\s+([a-zA-Z0-9_$]+))|"  # Group 1: Declarations
        r"(?:(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>|[a-zA-Z0-9_$]+\s*=>))",  # Group 2: Assignments
        re.MULTILINE,
    )

    all_functions = []

    for root, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".html"):
                file_path = os.path.join(root, file)

                try:
                    with open(file_path, encoding="utf-8") as f:
                        content = f.read()

                    # Find all <script> blocks
                    blocks = script_block_pattern.findall(content)

                    for block in blocks:
                        # Find all function variations in the block
                        matches = function_pattern.findall(block)

                        for match in matches:
                            # match is a tuple (group1, group2); pick whichever is not empty
                            func_name = match[0] or match[1]
                            if func_name:
                                all_functions.append(func_name)
                                print(f"{file_path}: {func_name}")

                except Exception as e:
                    print(f"Error reading {file_path}: {e}")

    print_duplicates(all_functions)


def print_duplicates(items):
    seen = set()
    duplicates = set()

    for item in items:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)

    if duplicates:
        print("Duplicates found:")
        for dup in sorted(list(duplicates)):
            print(dup)
    else:
        print("No duplicates found!")


# print_duplicates(my_list)

if __name__ == "__main__":
    # Runs in the current directory and all subdirectories
    find_all_js_functions("." + os.sep + "src" + os.sep + "web")
