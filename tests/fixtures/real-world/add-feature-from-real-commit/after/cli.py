import argparse

def cmd_list(args):
    print('listing nodes')
    return 0

def cmd_show(args):
    print('showing node', args.id)
    return 0

def cmd_resume(args):
    print('active claims:', _load_claims())
    print('ready queue (claim-aware):')
    return 0

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    l = sub.add_parser('list')
    l.set_defaults(func=cmd_list)
    s = sub.add_parser('show')
    s.add_argument('id')
    s.set_defaults(func=cmd_show)
    r = sub.add_parser('resume')
    r.set_defaults(func=cmd_resume)
    args = p.parse_args()
    return args.func(args)
