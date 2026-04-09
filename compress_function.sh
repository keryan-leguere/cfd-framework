#!/bin/bash

# Optimized tar+xz compression function with SLURM support
# Add this to your ~/.bashrc

compress() {
    # Usage check
    if [ $# -eq 0 ]; then
        echo "Usage: compress <folder_name/>"
        echo "Example: compress data/"
        echo "Output: data.tar.xz"
        return 1
    fi
    
    local input_folder="$1"
    
    # Remove trailing slash if present
    input_folder="${input_folder%/}"
    
    # Validate input folder exists
    if [ ! -d "$input_folder" ]; then
        echo "Error: Directory '$input_folder' not found"
        return 1
    fi
    
    # Generate output filename
    local output_file="${input_folder}.tar.xz"
    
    # Check if output already exists
    if [ -f "$output_file" ]; then
        echo "Warning: '$output_file' already exists"
        read -p "Overwrite? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted."
            return 1
        fi
        rm -f "$output_file"
    fi
    
    # Check if SLURM is available
    if command -v squeue &> /dev/null; then
        echo "SLURM detected. Checking 'essai' queue availability..."
        
        # Check available nodes in 'essai' partition
        local available_nodes=$(sinfo -p essai -h -o "%a %D" | grep idle | awk '{print $2}')
        
        if [ -n "$available_nodes" ] && [ "$available_nodes" -gt 0 ]; then
            echo "✓ $available_nodes idle node(s) available in 'essai' queue"
            echo "Submitting compression job to SLURM..."
            
            # Create temporary SLURM script
            local slurm_script=$(mktemp /tmp/compress_XXXXXX.sh)
            
            cat > "$slurm_script" << 'EOFSLURM'
#!/bin/bash
#SBATCH --job-name=compress
#SBATCH --partition=essai
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --output=compress_%j.log

# Get full CPU count of the node
NCPUS=$(nproc)

echo "=== Compression Job ==="
echo "Node: $(hostname)"
echo "CPUs available: $NCPUS"
echo "Input folder: INPUT_FOLDER"
echo "Output file: OUTPUT_FILE"
echo "Start time: $(date)"
echo "======================="

# Maximum compression with all available cores
tar -cvf - INPUT_FOLDER/ | xz -9 -T0 -vv > OUTPUT_FILE

EXITCODE=$?

echo "======================="
echo "End time: $(date)"
echo "Exit code: $EXITCODE"

if [ $EXITCODE -eq 0 ]; then
    echo "✓ Compression successful!"
    # Get file size
    SIZE=$(du -h OUTPUT_FILE | cut -f1)
    echo "Output size: $SIZE"
else
    echo "✗ Compression failed!"
fi

exit $EXITCODE
EOFSLURM
            
            # Replace placeholders
            sed -i "s|INPUT_FOLDER|$input_folder|g" "$slurm_script"
            sed -i "s|OUTPUT_FILE|$PWD/$output_file|g" "$slurm_script"
            
            # Submit job
            local job_id=$(sbatch --parsable "$slurm_script")
            
            if [ $? -eq 0 ]; then
                echo "✓ Job submitted successfully (Job ID: $job_id)"
                echo "Monitor with: squeue -j $job_id"
                echo "Log file: compress_${job_id}.log"
                echo "Cancel with: scancel $job_id"
            else
                echo "✗ Failed to submit SLURM job"
                rm -f "$slurm_script"
                return 1
            fi
            
            # Keep script for reference
            mv "$slurm_script" "compress_${job_id}.sh"
            
        else
            echo "✗ No idle nodes available in 'essai' queue"
            echo "Falling back to local compression (16 threads)..."
            _compress_local "$input_folder" "$output_file" 16
        fi
    else
        echo "SLURM not available. Using local compression (16 threads)..."
        _compress_local "$input_folder" "$output_file" 16
    fi
}

# Internal function for local compression
_compress_local() {
    local folder="$1"
    local output="$2"
    local threads="$3"
    
    echo "=== Local Compression ==="
    echo "Input: $folder/"
    echo "Output: $output"
    echo "Threads: $threads"
    echo "Compression level: 9 (maximum)"
    echo "Start: $(date)"
    echo "========================="
    
    # Maximum compression with specified threads
    # -9: maximum compression
    # -T: threads
    # -vv: very verbose to show progress
    # --extreme: extra compression (slower but better ratio)
    tar -cvf - "$folder/" | xz -9 -T"$threads" -vv --extreme > "$output"
    
    local exit_code=$?
    
    echo "========================="
    echo "End: $(date)"
    
    if [ $exit_code -eq 0 ]; then
        local size=$(du -h "$output" | cut -f1)
        local original_size=$(du -sh "$folder" | cut -f1)
        echo "✓ Compression successful!"
        echo "Original size: $original_size"
        echo "Compressed size: $size"
        
        # Calculate compression ratio if possible
        if command -v bc &> /dev/null; then
            local orig_bytes=$(du -sb "$folder" | cut -f1)
            local comp_bytes=$(stat -c%s "$output")
            local ratio=$(echo "scale=2; 100 - ($comp_bytes * 100 / $orig_bytes)" | bc)
            echo "Compression ratio: ${ratio}%"
        fi
    else
        echo "✗ Compression failed!"
        return $exit_code
    fi
}

# Autocomplete function for compress
_compress_autocomplete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    COMPREPLY=( $(compgen -d -- "$cur") )
}

# Register autocomplete
complete -F _compress_autocomplete compress


# ============================================
# BONUS: Additional utility functions
# ============================================

# Decompress function
decompress() {
    if [ $# -eq 0 ]; then
        echo "Usage: decompress <archive.tar.xz>"
        return 1
    fi
    
    local archive="$1"
    
    if [ ! -f "$archive" ]; then
        echo "Error: Archive '$archive' not found"
        return 1
    fi
    
    echo "Decompressing $archive..."
    tar -xvf "$archive"
}

# Check compression job status
compress_status() {
    if [ $# -eq 0 ]; then
        echo "Active compression jobs:"
        squeue -n compress -u $USER
    else
        local job_id="$1"
        echo "Status of job $job_id:"
        squeue -j "$job_id"
        echo ""
        echo "Latest log output:"
        tail -n 20 "compress_${job_id}.log" 2>/dev/null || echo "Log file not found"
    fi
}

# List all compression logs
compress_logs() {
    echo "Available compression logs:"
    ls -lht compress_*.log 2>/dev/null || echo "No logs found"
}

# Clean old compression logs and scripts
compress_clean() {
    echo "Cleaning old compression files..."
    rm -f compress_*.log compress_*.sh
    echo "Done."
}

# Show compression help
compress_help() {
    cat << 'EOF'
=== Compression Utilities ===

compress <folder/>
    Compress a folder using tar+xz with maximum compression.
    - Tries SLURM 'essai' queue first (uses all node CPUs with T0)
    - Falls back to local compression with 16 threads if no node available
    - Output: folder.tar.xz

decompress <archive.tar.xz>
    Decompress a tar.xz archive

compress_status [job_id]
    Check status of compression jobs
    - Without job_id: shows all active jobs
    - With job_id: shows specific job status and log tail

compress_logs
    List all compression log files

compress_clean
    Remove all compression logs and scripts

compress_help
    Show this help message

Examples:
    compress data/
    compress results/simulation_01/
    compress_status 123456
    decompress data.tar.xz

EOF
}
