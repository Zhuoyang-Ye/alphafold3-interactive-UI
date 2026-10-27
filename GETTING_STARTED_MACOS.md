# Getting started on a Mac (no Python experience needed)

This guide walks you through running AlphaFold 3 on your own Mac, step by step.
You do not need to know Python. You will copy and paste a handful of commands
into the **Terminal** app, and then do most of your work in a web page that
runs on your own computer.

When you finish, you will be able to:

- predict the 3D structure of proteins, DNA, RNA, and small molecules;
- look at the results in an interactive 3D viewer;
- see which parts of two molecules touch, and how confident the model is.

Everything stays on your Mac. Nothing is uploaded anywhere.

> **Want to see it before installing?** Try the read-only
> [online demo](https://zhuoyang-ye.github.io/alphafold3-interactive-UI/). It
> shows the explorer with a few saved structures. Running your own predictions
> needs the setup below.

---

## Before you start: what you need

| Requirement | Why |
| --- | --- |
| A Mac with an **Apple Silicon** chip (M1, M2, M3, M4 or newer) | The setup uses the Mac's built-in GPU. To check, open the  menu → **About This Mac**. The "Chip" line should say *Apple M…*. |
| About **650 GB of free disk space** (an external SSD is fine) | The sequence databases AlphaFold 3 searches are very large: ~252 GB to download, ~630 GB once unpacked. |
| A reliable internet connection and a few hours | The database download is the slow part. You only do it once. |
| As much memory (RAM) as possible | Larger molecules and full database searches need more memory. Start with small proteins. |

> **How long will this take?** Steps 1–4 take about 20–30 minutes of active
> time. Step 5 (the databases) runs by itself for several hours.

---

## How to use the Terminal (30-second primer)

1. Open **Terminal**: press `⌘ Command` + `Space`, type `Terminal`, press `Return`.
2. Each grey box below is a command. Copy it, paste it into Terminal
   (`⌘ Command` + `V`), and press `Return`.
3. Wait until the command finishes. You will know it is done when you see your
   prompt again (a line ending in `%`). Then go on to the next one.
4. If Terminal asks for your **password**, type your Mac login password and
   press `Return`. Nothing appears on screen while you type. This is normal.

Lines starting with `#` inside the boxes are comments; Terminal ignores them.

---

## Step 1: Install the developer tools and Homebrew

Homebrew is a free installer for command-line tools. It also installs Apple's
developer tools, which AlphaFold 3 needs to build one of its parts.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes, Homebrew prints a **"Next steps"** section with two or three
commands that start with `echo` or `eval`. **Copy and run those too**, then
close Terminal and open it again.

Check that it worked:

```bash
brew --version
```

You should see something like `Homebrew 4.x.x`.

## Step 2: Install the search tools

AlphaFold 3 uses **HMMER** to search the databases. `wget` and `zstd` are used
to download and unpack them.

```bash
brew install hmmer wget zstd
```

## Step 3: Install uv (this takes care of Python for you)

`uv` downloads the right version of Python and every package AlphaFold 3
needs, and keeps them inside the AlphaFold 3 folder. It will not change
anything else on your Mac.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close Terminal and open it again, then check:

```bash
uv --version
```

## Step 4: Set up AlphaFold 3

### 4a. Go into the AlphaFold 3 folder

If you downloaded a ZIP file, double-click it to unzip it first. Then, in
Terminal, type `cd` followed by a space, **drag the `alphafold3` folder
from Finder onto the Terminal window**, and press `Return`. For example:

```bash
cd ~/Downloads/alphafold3
```

All remaining commands must be run from inside this folder. If you close
Terminal, run this `cd` command again when you come back.

### 4b. Install AlphaFold 3 and its packages

```bash
uv sync
uv run build_data
```

The first command downloads Python and all packages, then builds AlphaFold 3.
It can take 5–15 minutes. The second prepares a chemistry dictionary that
AlphaFold 3 uses. Some warnings in yellow are normal. Only a message ending in
`error` means something went wrong.

### 4c. Get the model weights

The "weights" are the trained model itself: one file of about 1 GB. Read the
[terms of use](WEIGHTS_TERMS_OF_USE.md) first. The download location and the
latest instructions are in
[docs/installation.md → Obtaining Model Parameters](docs/installation.md#obtaining-model-parameters).

Put the file in a folder called `models` in your home folder:

```bash
mkdir -p ~/models
# Move the downloaded file there, for example:
mv ~/Downloads/af3.bin.zst ~/models/
```

You do **not** need to unpack the `.zst` file. AlphaFold 3 reads it as it is.

## Step 5: Download the databases (several hours)

This step downloads ~252 GB and unpacks it to ~630 GB. Keep your Mac plugged in
and stop it from going to sleep while this runs (**System Settings → Lock
Screen / Battery → Prevent automatic sleeping**).

To use the default location (`public_databases` in your home folder):

```bash
bash fetch_databases_macos.sh
```

Or to put them on an external drive (replace `MyDrive` with your drive's name,
as shown in Finder):

```bash
bash fetch_databases_macos.sh /Volumes/MyDrive/public_databases
```

When it prints `Complete`, you are done. If it prints `FAILED`, run the same
command again.

> **Why `fetch_databases_macos.sh` and not `fetch_databases.sh`?** The original
> script uses options that the Mac's built-in tools do not support. This copy
> fixes that and otherwise downloads exactly the same files.

---

## Step 6: Start the explorer (the easy way to use AlphaFold 3)

The explorer is a web page that runs only on your Mac. It lets you start
predictions, watch their progress, and look at the results in 3D, all without
the Terminal.

```bash
bash run_explorer.sh
```

If you put the databases or weights somewhere other than the default, say where:

```bash
bash run_explorer.sh --db-dir /Volumes/MyDrive/public_databases --model-dir ~/models
```

Now open **<http://127.0.0.1:8765>** in Safari or Chrome.

**Leave the Terminal window open** while you use the explorer. Closing it, or
pressing `Control` + `C` in it, stops the explorer.

### Your first prediction

1. Click **New experiment**.
2. Pick the **Ubiquitin** example, a small 76-residue protein.
3. Under **Run mode**, choose **Sequence-only prediction** for a first check
   that everything works. It skips the slow database search. The result is
   only a test and is not a reliable structure.
4. Click **Add to queue →** and watch the live log under **Experiments**.
5. When it finishes, the structure appears in your library. Click it to view it
   in 3D. The colors show the model's confidence (blue = confident,
   orange = not confident).

Once that works, try **Search databases + predict**. This is the normal,
accurate mode. A database search can take from tens of minutes to several
hours, depending on the size of the molecule and your Mac.

### Choosing your own molecules

Click **New experiment**, then **+ Custom input**, and use **Find a molecule**:

1. Pick a type: **Protein**, **DNA**, **RNA**, **Ligand**, or **Ion**. With the
   search box empty, you see the molecules studied most often.
2. Or type a name (`hemoglobin`, `tRNA`, `ATP`), a PDB ID (`1QPI`), or paste a
   sequence.
3. Click **Add**. To copy a whole known complex, click one of its PDB IDs and
   then **Add selected**.

The first time the explorer starts, it spends about a minute building this
catalog from your downloaded files. DNA usually needs both strands; the
**+ Complementary strand** button adds the matching one for you.

To remove an experiment you no longer need, open it under **Experiments** and
click **Delete**.

The explorer can also:

- show which residues of two chains are in contact, and export them as a table;
- compare two structures side by side;
- color a protein by how conserved each position is across evolution;
- import results from earlier AlphaFold 3 runs or from the PDB.

See [explorer/README.md](explorer/README.md) for details on each feature.

---

## Optional: run a prediction from the Terminal instead

You can skip this section if you use the explorer.

AlphaFold 3 reads a small text file (in JSON format) describing your molecules.
The command below creates one for ubiquitin in your home folder:

```bash
cat > ~/ubiquitin.json <<'EOF'
{
  "name": "ubiquitin",
  "modelSeeds": [1],
  "sequences": [
    {"protein": {"id": "A", "sequence": "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"}}
  ],
  "dialect": "alphafold3",
  "version": 4
}
EOF
```

Then run it. The full search and prediction can take a while:

```bash
bash run_af3_macos.sh ~/ubiquitin.json
```

The results go into a folder called `af_output` inside the AlphaFold 3 folder.
The main structure file ends in `_model.cif`. You can open it in the explorer
(click **+** in the library), or in free viewers such as
[Mol*](https://molstar.org/viewer/) or ChimeraX.

If your databases or weights are not in the default places:

```bash
DB_DIR=/Volumes/MyDrive/public_databases MODEL_DIR=~/models bash run_af3_macos.sh ~/ubiquitin.json
```

The full input format, with DNA, RNA, ligands and modifications, is described in
[docs/input.md](docs/input.md). The output files are explained in
[docs/output.md](docs/output.md).

---

## Troubleshooting

| What you see | What to do |
| --- | --- |
| `command not found: brew` | Run the "Next steps" commands Homebrew printed at the end of Step 1, then reopen Terminal. |
| `command not found: uv` | Close and reopen Terminal after Step 3. |
| `No such file or directory: run_explorer.sh` (or another script) | You are not in the AlphaFold 3 folder. Repeat Step 4a. |
| `.venv/bin/python: No such file or directory` | Step 4b did not finish. Run `uv sync` again from the AlphaFold 3 folder. |
| The browser says it can't connect to 127.0.0.1:8765 | The explorer is not running. Check that the Terminal window from Step 6 is still open and shows no error. |
| `Address already in use` | The explorer is already running in another Terminal window, or another app is using the port. Use `bash run_explorer.sh --port 8766` and open <http://127.0.0.1:8766>. |
| Errors about missing database files | The database path is wrong, or Step 5 did not finish. Check the folder exists and pass it with `--db-dir`. |
| Errors about model parameters / weights | The weights are not in `~/models`. Check the file is there, or pass `--model-dir`. |
| Your Mac becomes very slow, or the run stops | The molecule is probably too big for your Mac's memory. Try a smaller molecule, or close other apps. |

Known issues with the Mac GPU backend (which is experimental) are listed in
[docs/known_issues.md](docs/known_issues.md).

---

## Words you may see

- **Terminal**: the Mac app where you type commands.
- **Database search / MSA**: AlphaFold 3 looks for related sequences in other
  organisms. This greatly improves accuracy and is the slowest step.
- **Weights / model parameters**: the trained AlphaFold 3 model, a single file.
- **mmCIF (`.cif`)**: the standard file format for 3D molecular structures.
- **pLDDT**: per-residue confidence, from 0 to 100. Higher is better.
- **pTM / ipTM**: overall confidence scores for the whole structure, and for
  how chains fit together. Higher is better.
- **PAE**: a heatmap of how confident the model is about the relative position
  of each pair of residues. Darker / lower values are better.
- **Seed**: a number that changes the random starting point. Running several
  seeds and comparing them is good practice.

## Please note

- Predictions are models, not experimental measurements. Contacts and
  confidence scores do not by themselves prove that molecules bind.
- AlphaFold 3 code, weights and outputs are subject to the terms in this folder:
  [LICENSE](LICENSE), [WEIGHTS_TERMS_OF_USE.md](WEIGHTS_TERMS_OF_USE.md),
  [WEIGHTS_PROHIBITED_USE_POLICY.md](WEIGHTS_PROHIBITED_USE_POLICY.md) and
  [OUTPUT_TERMS_OF_USE.md](OUTPUT_TERMS_OF_USE.md).
