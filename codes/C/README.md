mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Debug ..           # or Dev, Release, ReleaseHardened
cmake --build .
ln -sf build/compile_commands.json ..
