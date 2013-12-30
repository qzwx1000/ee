import os

from model import RouterDef, SocketDef, JtagEntry

def getChain(assem):
    jtag_entry_boards = [(boardname, abrd.boarddef.jtag_entry) for boardname, abrd in assem.boards.iteritems() if abrd.boarddef.jtag_entry]

    if len(jtag_entry_boards) == 0:
        raise Exception("Error: no boards have jtag entries so this assembly is not programmable!")
    if len(jtag_entry_boards) > 1:
        raise Exception("Too many jtag entry boards; found %s" % jtag_entry_boards)

    chain = []

    jtag_entry, = jtag_entry_boards

    cur_board = jtag_entry[0]
    cur_idx = jtag_entry[1].jtag

    while True:
        print "At", cur_board, cur_idx
        new_idx = cur_idx + 1

        boarddef = assem.boards[cur_board].boarddef
        if new_idx not in boarddef.jtags:
            # Wrapping around to the main connector:
            assert new_idx == len(boarddef.jtags) + 1
            connections = assem.connections[cur_board]
            if None not in connections:
                print "Skipping connector for %s; it better be bypassed" % cur_board
                cur_board, cur_idx = cur_board, 0
            else:
                new_board, new_board_socket = connections[None]
                new_board_socket = assem.boards[new_board].boarddef.sockets[new_board_socket]
                cur_board, cur_idx = new_board, new_board_socket.jtag
        else:
            jobj = boarddef.jtags[new_idx]
            if isinstance(jobj, RouterDef):
                chain.append("%s.%s" % (cur_board, jobj.name))
                cur_board, cur_idx = cur_board, new_idx
            elif isinstance(jobj, SocketDef):
                # TODO duplicated with the connector code above
                connections = assem.connections[cur_board]
                if jobj.name not in connections:
                    print "Skipping socket %s for %s; it better be bypassed" % (jobj.name, cur_board)
                    cur_board, cur_idx = cur_board, new_idx
                else:
                    new_board, new_board_socket = connections[jobj.name]
                    new_board_socket = assem.boards[new_board].boarddef.sockets[new_board_socket]
                    cur_board, cur_idx = new_board, new_board_socket.jtag
            elif isinstance(jobj, JtagEntry):
                break
            else:
                raise Exception(jobj)
    return chain

def doOutput(assem, rn, of):
    print assem, rn, of

    build_dir = assem.name
    if not os.path.isdir(build_dir):
        os.makedirs(build_dir)

    for rname, router in rn.routers.items():
        base_fn = os.path.join(build_dir, rname)

        tmpdir = os.path.join(build_dir, "xst_%s/projnav.tmp" % rname)
        if not os.path.isdir(tmpdir):
            os.makedirs(tmpdir)

        print rname, router
        with open("%s.v" % base_fn, 'w') as f:
            print >>f, "`timescale 1ns / 1ps"
            print >>f
            print >>f, "module main("

            first = 1
            for target, source in router.iteritems():
                if not first:
                    print >>f, ','
                first = 0
                print >>f, "  input p%s," % source
                print >>f, "  output p%s" % target,
            print >>f, ");"

            for target, source in router.iteritems():
                print >>f, "  assign p%s = p%s;" % (target, source)

            print >>f, "endmodule"

        with open("%s.xst" % base_fn, 'w') as f:
            print >>f, ("""
set -tmpdir "xst_%(rname)s/projnav.tmp"
set -xsthdpdir "xst_%(rname)s"
run
-ifn %(rname)s.prj
-ifmt mixed
-ofn %(rname)s.ngc
-ofmt NGC
-p xbr
-top main
-opt_mode Speed
-opt_level 1
-iuc NO
-keep_hierarchy Yes
-netlist_hierarchy As_Optimized
-rtlview Yes
-hierarchy_separator /
-bus_delimiter <>
-case Maintain
-verilog2001 YES
-fsm_extract YES -fsm_encoding Auto
-safe_implementation No
-mux_extract Yes
-resource_sharing YES
-iobuf YES
-pld_mp YES
-pld_xp YES
-pld_ce YES
-wysiwyg NO
-equivalent_register_removal YES
""" % dict(rname=rname)).strip()

            with open("%s.prj" % base_fn, 'w') as f:
                print >>f, 'verilog work "%s.v"' % base_fn

            with open("%s.ucf" % base_fn, 'w') as f:
                pins = []
                for target, source in router.iteritems():
                    pins.append(source)
                    pins.append(target)

                for pin in pins:
                    print >>f, 'net "p%s" LOC="%s" | IOSTANDARD = "LVCMOS33";' % (pin, pin)

        print >>of, "%s.ngc: %s.v" % (base_fn, base_fn)
        print >>of, "\t$(ISE_BIN)/xst -intstyle ise -ifn %s.xst" % (base_fn)
        print >>of, "%s.ngd: %s.ngc" % (base_fn, base_fn)
        print >>of, "\t$(ISE_BIN)/ngdbuild -uc %s.ucf -p xc2c64a-7-vq100 %s.ngc %s.ngd" % (base_fn, base_fn, base_fn)
        print >>of, "%s.vm6: %s.ngd" % (base_fn, base_fn)
        print >>of, "\t$(ISE_BIN)/cpldfit -p xc2c64a-7-vq100 %s.ngd" % (base_fn)
        print >>of, "%s.jed: %s.vm6" % (base_fn, base_fn)
        print >>of, "\t$(ISE_BIN)/hprep6 -i %s.vm6" % (base_fn)
# %.vm6: %.ngd
		# $(ISE_BIN)/cpldfit $(CPLDFIT_FLAGS) -p $(PART) $*.ngd
# %.jed: %.vm6
		# $(ISE_BIN)/hprep6 $(HPREP6_FLAGS) -i $*.vm6

    chain = getChain(assem)
    assert len(chain) == len(rn.routers)

    print chain
    print rn.routers

    # 1/0

