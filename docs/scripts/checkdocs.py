#!/usr/bin/env python
import optparse, subprocess, sys, os, re, glob

links = {}
symbols = {}
structs = {}
types = {}
anonymous_enums = {}
functions = {}

def check_references():
    """
    Check if each [link] in the reference manual actually exists. Also fills
    in global variable "links".
    """
    print("Checking References...")
    
    html_refs = os.path.join(options.path, "docs", "html_refs")
    for line in open(html_refs):
        mob = re.match(r"\[(.*?)\]", line)
        if mob:
            links[mob.group(1)] = True

    docs = glob.glob("docs/src/refman/*.txt")
    for doc in docs:
        text =  file(doc).read()
        text = re.compile("<script.*?>.*?</script>", re.S).sub("", text)
        for link in re.findall(r" \[(.*?)\][^(]", text):
            if not link in links:
                print("Missing: %s: %s" % (doc, link))

def add_struct(line):
    if options.protos:
        kind = re.match("\s*(\w+)", line).group(1)
        if kind in ["typedef", "struct", "enum", "union"]:
            mob = None
            if kind != "typedef":
                mob = re.match(kind + "\s+(\w+)", line)
            if not mob: mob = re.match(".*?(\w+);$", line)
            if not mob and kind == "typedef":
                mob = re.match("typedef.*?\(\s*\*\s*(\w+)\)", line)
            if not mob:
                anonymous_enums[line] = 1
            else:
                sname = mob.group(1)
                if sname.startswith("_ALLEGRO_gl"): return
                if kind == "typedef":
                    types[sname] = line
                else:
                    structs[sname] = line

def parse_header(lines, filename):
    """
    Minimal C parser which extracts most symbols from a header. Fills
    them into the global variable "symbols".
    """
    n = 0
    ok = False
    brace = 0
    lines2 = []
    cline = ""
    for line in lines:
        line = line.strip()
        if not line: continue

        if line.startswith("#"):
            if line.startswith("#define"):
                if ok:
                    name = line[8:]
                    symbols[name] = "macro"
                    n += 1
            elif line.startswith("#undef"):
                pass
            else:
                match = re.match(r'# \d+ "(.*?)"', line)
                name = match.group(1)
                if name == "<stdin>" or name.startswith(options.build) or \
                    name.startswith("include") or name.startswith("addons"):
                    ok = True
                else:
                    ok = False
            continue
        if not ok: continue

        sublines = line.split(";")

        for i, subline in enumerate(sublines):
            if i < len(sublines) - 1:
                subline += ";"

            brace -= subline.count("}")
            brace -= subline.count(")")
            brace += subline.count("{")
            brace += subline.count("(")

            if brace == 0 and subline.endswith(";") or subline.endswith("}"):
                cline += subline
                lines2.append(cline.strip())
                cline = ""
            else:
                cline += subline

    for line in lines2:
        if line.startswith("enum"):
            add_struct(line)
        elif line.startswith("typedef"):
            match = None
            if not match:
                match = re.match(r".*?(\w+);$", line)
            if not match:
                match = re.match(r".*?(\w*)\[", line)
            if not match:
                match = re.match(r".*?\(\s*\*\s*(\w+)\s*\).*?", line)

            if match:
                name = match.group(1)
                symbols[name] = "typedef"
                n += 1
            else:
                print(line)

            add_struct(line)

        elif line.startswith("struct"):
            add_struct(line)
        elif line.startswith("union"):
            add_struct(line)
        else:
            try:
                parenthesis = line.find("(")
                if parenthesis < 0:
                    match = re.match(r".*?(\w+)\s*=", line)
                    if not match:
                        match = re.match(r".*?(\w+)\s*;$", line)
                    if not match:
                        match = re.match(r".*?(\w+)", line)
                    symbols[match.group(1)] = "variable"
                    n += 1
                else:
                    match = re.match(r".*?(\w+)\s*\(", line)
                    fname = match.group(1)
                    symbols[fname] = "function"
                    if not fname in functions:
                        functions[fname] = line
                    n += 1
            except AttributeError, e:
                print("Cannot parse in " + filename)
                print("Line is: " + line)
                print(e)
    return n

def parse_all_headers():
    """
    Call parse_header() on all of Allegro's public include files.
    """
    includes = " -I include -I " + os.path.join(options.build, "include")
    includes += " -I addons/acodec"
    headers = ["include/allegro5/allegro5.h",
        "addons/acodec/allegro5/allegro_flac.h",
        "addons/acodec/allegro5/allegro_vorbis.h",
        "include/allegro5/allegro_opengl.h"]

    for addon in glob.glob("addons/*"):
        name = addon[7:]
        header = os.path.join("addons", name, "allegro5",
            "allegro_" + name + ".h")
        if os.path.exists(header):
            headers.append(header)
            includes += " -I " + os.path.join("addons", name)

    for header in headers:
        p = subprocess.Popen("gcc -E -dN - " + includes,
            stdout = subprocess.PIPE, stdin = subprocess.PIPE, shell = True)
        p.stdin.write("#include <allegro5/allegro5.h>\n" + open(header).read())
        p.stdin.close()
        text = p.stdout.read()
        n = parse_header(text.splitlines(), header)
        #print("%d definitions in %s" % (n, header))

def check_undocumented_functions():
    """
    Cross-compare the documentation links with public symbols found in headers.
    """
    print("Checking if each documented function exists...")

    parse_all_headers()

    for link in links:
        if not link in symbols:
            print("Missing: " + link)

    print("")
    print("Checking if each function is documented...")
    others = []
    for link in symbols:
        if not link in links:
            if symbols[link] == "function":
                print("Missing: " + link)
            else:
                if link and not link.startswith("GL") and \
                    not link.startswith("gl") and \
                    not link.startswith("_al_gl") and \
                    not link.startswith("_ALLEGRO_gl") and \
                    not link.startswith("_ALLEGRO_GL") and \
                    not link.startswith("ALLEGRO_"):
                    others.append(link)

    print("Also leaking:")
    others.sort();
    print(", ".join(others))

def list_all_symbols():
    parse_all_headers()
    for name in sorted(symbols.keys()):
        print(name)

def main(argv):
    global options
    p = optparse.OptionParser()
    p.description = """\
When run from the toplevel A5 directory, this script will parse the include,
addons and cmake build directory for global definitions and check against all
references in the documentation - then report symbols which are not documented.
""";
    p.add_option("-b", "--build", help = "Path to the build directory.")
    p.add_option("-l", "--list", action = "store_true", help = "List all symbols.")
    p.add_option("-p", "--protos",  help = "Write all public " +
        "prototypes to the given file.")
    options, args = p.parse_args()

    if not options.build:
        sys.stderr.write("Build path required (-p).\n")
        p.print_help()
        sys.exit(-1)

    if options.protos:
        parse_all_headers()
        f = open(options.protos, "w")
        for name, s in structs.items():
            f.write(name + ": " + s + "\n")
        for name, s in types.items():
            f.write(name + ": " + s + "\n")
        for e in anonymous_enums.keys():
            f.write(": " + e + "\n")
        for fname, proto in functions.items():
            f.write(fname + "(): " + proto + "\n")
    elif options.list:
        list_all_symbols()
    else:
        check_references()
        print("")
        check_undocumented_functions()

if __name__ == "__main__":
    main(sys.argv)

