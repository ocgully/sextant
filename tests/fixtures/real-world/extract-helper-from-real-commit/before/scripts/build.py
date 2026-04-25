def build_bundle(project_root, marketplaces):
    out_dir = project_root / '.claude' / 'agents'
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for mp in marketplaces:
        for agent_file in (mp / 'agents').glob('*.md'):
            if agent_file.name in seen:
                continue
            seen.add(agent_file.name)
            (out_dir / agent_file.name).write_text(agent_file.read_text())
    return out_dir
