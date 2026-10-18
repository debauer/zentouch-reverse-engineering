# Example

Complete run for `ZenTouchP4S_PCFW_LF_2_10_05.exe`, from the repository root. Get the keys from
Rockbox first (`tools.md`, section Keys).

    export ZEN_TL_KEY='...' ZEN_FRESC_KEY='...' ZEN_SIGNING_KEY='...'
    python3 scripts/init_dirs.py
    cp /path/to/ZenTouchP4S_PCFW_LF_2_10_05.exe input/firmware/

    # extract -> output/extracted/ZenTouchP4S_PCFW_LF_2_10_05_extracted/
    #   TL.enc FRESC FBOOT Pmcu0 CINF.bin NULL.bin H* firmware.ciff manifest.json
    python3 scripts/extract_zen_firmware.py input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe

    # self test -> output/roundtrip/ZenTouchP4S_PCFW_LF_2_10_05_roundtrip/ (report.json, rebuilt.ciff)
    python3 scripts/roundtrip_zen_touch.py input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe

    # decrypt -> output/Jukebox2.jrm, output/FRESC.decrypted.bin
    E=output/extracted/ZenTouchP4S_PCFW_LF_2_10_05_extracted
    python3 scripts/decrypt_zen_touch.py $E/TL.enc -o output/Jukebox2.jrm
    python3 scripts/decrypt_zen_touch.py $E/FRESC -m FRESC -o output/FRESC.decrypted.bin

    # code blocks -> output/code/Jukebox2_code_blocks/block_NN_<address>.bin (15 blocks)
    python3 scripts/export_zen_code.py output/Jukebox2.jrm

    # (edit output/Jukebox2.jrm here; fix the CODE record checksums afterwards)

    # rebuild: encrypt, pack, update EXE
    python3 scripts/encrypt_zen_touch.py output/Jukebox2.jrm -o output/TL.new
    mkdir output/work && cp $E/* output/work/ && cp output/TL.new output/work/TL.enc
    python3 scripts/pack_zen_firmware.py output/work -o output/new.ciff
    python3 scripts/make_zen_update.py -u input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe \
        -f output/new.ciff -o output/updates/ZenTouchP4S_PCFW_LF_2_10_05_new.exe

    # verify with the Rockbox tools (needs cmake and a Rockbox checkout in rockbox/)
    git clone https://github.com/Rockbox/rockbox.git rockbox
    bash scripts/build_rockbox_zencrypt.sh
    python3 scripts/verify_rockbox_zencrypt.py \
        --roundtrip output/roundtrip/ZenTouchP4S_PCFW_LF_2_10_05_roundtrip
    python3 scripts/verify_zen_update.py \
        -u input/firmware/ZenTouchP4S_PCFW_LF_2_10_05.exe -f output/new.ciff

Not tested on a device; read `tools.md` and `update_and_flash.md` before flashing.
