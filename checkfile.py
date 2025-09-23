import pefile

pe = pefile.PE(r"C:\Program Files\Swift\Imaging\x64\swiftcam.dll")
for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
    print(exp.name)
