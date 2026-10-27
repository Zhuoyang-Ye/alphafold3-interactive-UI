#!/bin/bash
# macOS-adapted variant of the upstream fetch_databases.sh for AlphaFold 3.
#
# Why this file exists (upstream script does not run on macOS):
#   1. Upstream uses `tar --use-compress-program=zstd`. That is a GNU tar
#      option; Apple's bsdtar does not support it and silently tries to read
#      the compressed stream as a raw archive ("Unrecognized archive format").
#      Fixed here by decompressing with zstd into a pipe.
#   2. Upstream ends with `wait -n`, which needs bash >= 4.3. macOS ships
#      bash 3.2, where it errors with "wait: -n: invalid option".
#      Fixed here by waiting on each recorded PID and reporting failures.
#
# Usage: ./fetch_databases_macos.sh [<DB_DIR>]   (default: $HOME/public_databases)

set -euo pipefail

readonly db_dir=${1:-$HOME/public_databases}

for cmd in wget tar zstd ; do
  if ! command -v "${cmd}" > /dev/null 2>&1; then
    echo "${cmd} is not installed. Please install it."
    exit 1
  fi
done

echo "Fetching databases to ${db_dir}"
mkdir -p "${db_dir}"

readonly SOURCE=https://storage.googleapis.com/alphafold-databases/v3.0

pids=()
names=()

echo "Start Fetching and Untarring 'pdb_2022_09_28_mmcif_files.tar'"
wget --quiet --output-document=- \
    "${SOURCE}/pdb_2022_09_28_mmcif_files.tar.zst" | \
    zstd --decompress --stdout | \
    tar --no-same-owner --no-same-permissions \
    -xf - --directory="${db_dir}" &
pids+=($!)
names+=("pdb_2022_09_28_mmcif_files")

for NAME in mgy_clusters_2022_05.fa \
            bfd-first_non_consensus_sequences.fasta \
            uniref90_2022_05.fa \
            uniprot_all_2021_04.fa \
            pdb_seqres_2022_09_28.fasta \
            rnacentral_active_seq_id_90_cov_80_linclust.fasta \
            nt_rna_2023_02_23_clust_seq_id_90_cov_80_rep_seq.fasta \
            rfam_14_9_clust_seq_id_90_cov_80_rep_seq.fasta ; do
  echo "Start Fetching '${NAME}'"
  wget --quiet --output-document=- "${SOURCE}/${NAME}.zst" | \
      zstd --decompress > "${db_dir}/${NAME}" &
  pids+=($!)
  names+=("${NAME}")
done

failed=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then
    echo "FAILED: ${names[$i]}" >&2
    failed=1
  fi
done

if [ "${failed}" -ne 0 ]; then
  echo "One or more database downloads failed." >&2
  exit 1
fi

echo "Complete"
