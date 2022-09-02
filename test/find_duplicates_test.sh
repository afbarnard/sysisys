# Minimally tests `find_duplicates.py` and the script it generates

# Exit immediately on errors.  Trace errors.
set -eE

# Trap errors and provide a call stack
trap 'print_traceback ${?} "${BASH_COMMAND}" ${LINENO} >&2' ERR

# Print a traceback
function print_traceback() {
    echo "Traceback:"
    for ((i=$((${#BASH_SOURCE[@]} - 1)); i>=1; i--)); do
        printf '  %s:%4i: %s()\n' "${BASH_SOURCE[$((i-1))]}" ${BASH_LINENO[i]} ${FUNCNAME[i]}
    done
    printf '  %s:%4i: %s\n' "${BASH_SOURCE[0]}" ${3} "${2}"
    echo "Error: ${1}"
}

# Log the given arguments as a message
function log() {
    echo "$(date +'%FT%T') find_dups_test: ${@}" >&2
}

# Log the given arguments as an error and die
function die() {
    log "Error: ${@}"
    exit 1
}

# Whether two files have equal extents.  The filename must be removed
# from the output of `filefrag` for it to compare equal.
function equal_extents() {
    cmp --quiet <(filefrag -ev "${1}" | grep -v -F "${1}") \\
                <(filefrag -ev "${2}" | grep -v -F "${2}")
}

function create_links() {
    # Create various links
    ln "${1}" "${1}.hardlink"
    ln -rs "${1}" "${1}.symlink"
    cp --reflink=always "${1}" "${1}.reflink"
}

function create_xattrs() {
    setfattr -n user.filename -v "${1}" "${1}"
    setfattr -n user.inode -v $(stat --format '%i' "${1}") "${1}"
}

# TODO test files: inline, empty, large, 1 bit differences both in head and tail and on boundary
# TODO write tests in Python, use chunk of tmpfs to make btrfs
# TODO test deduping of symlink against original

function create_test_files() {
    log "Creating test files in directory: '${1}'"
    # Create some building blocks (but don't use up too much randomness)
    head --bytes 1K /dev/urandom > "${1}/block1"
    tac "${1}/block1" > "${1}/block2"
    # Make 128K original files by repeating a block
    yes "${1}/block1" | head -n 128 | xargs cat > "${1}/copy1"
    yes "${1}/block2" | head -n 128 | xargs cat > "${1}/copy2"

    # Create copies
    mkdir "${1}/dir"
    cp "${1}/copy"{1,3}
    cp "${1}/copy1" "${1}/dir/copy4"
    cp "${1}/block"{1,3}
    cp "${1}/block"{2,4}

    # Create links
    create_links "${1}/copy1"
    create_links "${1}/copy3"
    create_links "${1}/dir/copy4"

    # Create distractors of the same size but different contents
    head --bytes 1K /dev/zero > "${1}/block0"
    head --bytes 128K /dev/zero > "${1}/copy0"
    base64 "${1}/copy1" | head --bytes 128K > "${1}/base64"
    rev "${1}/base64" > "${1}/dir/46esab"

    # Create unique xattrs
    for file in $(find "${1}" -type f); do
        create_xattrs "${file}"
    done
}

function test_find_duplicates() {
    log "test_find_duplicates: Start"
    # Create a temporary directory in which to place files
    tmp_dir=$(mktemp --directory ztest.find_duplicates.XXXXXXX)
    # Create files
    files_dir="${tmp_dir}/files"
    mkdir "${files_dir}"
    create_test_files "${files_dir}"
    return

    # Run `find_duplicates.py`
    (
        cd "${tmp_dir}"
        python3 "${src_dir}/find_duplicates.py" --db dedup.sqlite --dedup btrfs --min-size 1 --pick-original-by='cli,mtime,n_links>,depth,path' files 1>dedup.sh 2>dedup.log
    )

    # Check log
    log_file="${tmp_dir}/dedup.log"
    grep -q 'Scanned 13 files' "${log_file}" # Excludes symlinks
    grep -q 'Calculated 30 checksums' "${log_file}" # 9 + 3 + 9 * 2
    grep -q 'Retrieved extents of 9 files' "${log_file}"

    # Compare generated output
    tmp_dir_abs="$(cd "${tmp_dir}"; pwd)"
    cat - > "${tmp_dir}/dedup.sh.expected" <<EOF
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/copy2
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/copy2.hardlink
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/copy2.reflink
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/dir/copy3
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/dir/copy3.hardlink
dedup ${tmp_dir_abs}/files/copy1 ${tmp_dir_abs}/files/dir/copy3.reflink
EOF
    tail -n 8 "${tmp_dir}/dedup.sh" | sed -e 's/ *#.*//' -e '/^$/d' | sort > "${tmp_dir}/dedup.sh.actual"
    diff -u "${tmp_dir}/dedup.sh.expected" "${tmp_dir}/dedup.sh.actual" > "${tmp_dir}/dedup.sh.diff"

    # Cleanup
    rm -Rf "${tmp_dir}"
    log "test_find_duplicates: Done"
}

# Setup
this_dir=$(cd $(dirname "${0}"); pwd)
src_dir=$(dirname "${this_dir}")
#log "src_dir: '${src_dir}'"

# Run tests
test_find_duplicates
