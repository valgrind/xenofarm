#!/usr/bin/env python

import os
import stat
import time

import MySQLdb

import updatehtml_cfg
import updatehtml_templates

_DB = None

def init():
    global _DB
    pwd = open(updatehtml_cfg.dbpwdfile, "r").readline()
    if pwd[-1] == "\n":
        pwd = pwd[:-1]
    _DB = MySQLdb.connect(db=updatehtml_cfg.dbname,
                          user=updatehtml_cfg.dbuser,
                          host=updatehtml_cfg.dbhost,
                          passwd=pwd)


def get_systems_for_latest():
    cursor = _DB.cursor()
    cursor.execute("select -max(build.id),"
                   "     concat(system.sysname, ' ', system.machine),"
                   "     system.release,"
                   "     system.testname,"
                   "     system.name,"
                   "     system.id,"
                   "     max(build.time)"
                   " from system, build, task_result"
                   " where task_result.system = system.id"
                   " and task_result.build = build.id"
                   " group by system.id")
    rows = cursor.fetchall()
    cursor.close()
    rows = list(rows)
    rows.sort()
    return [build_sys_info(-row[0], row[-1], system(*row[1:-1]))
            for row in rows]

class build_sys_info:
    def __init__(self, buildid, buildtime, sysinfo):
        self.buildid = buildid
        self.buildtime = buildtime
        self.sysinfo = sysinfo

def get_all_tasks_for_builds(builds):
    cursor = _DB.cursor()
    cursor.execute("select distinct task_result.task, task.name"
                   " from system, build, task_result, task"
                   " where task_result.system = system.id"
                   " and task_result.build = build.id"
                   " and task_result.task = task.id"
                   " and build.id in (%s)"
                   " order by task.sort_order" % (
                       ", ".join(["%d" % x for x in builds])))
    rows = cursor.fetchall()
    cursor.close()
    return rows

def get_all_tasks_for_system(systemid):
    cursor = _DB.cursor()
    cursor.execute("select distinct task_result.task, task.name"
                   " from task_result, task"
                   " where task_result.system = %s"
                   " and task_result.task = task.id"
                   " order by task.sort_order" % (systemid))
    rows = cursor.fetchall()
    cursor.close()
    return rows

def latest_heading_row(tasks):
    res = ["  <tr>",
           "    <th>Machine<br><font size=-1>(build details)</font></th>"]
    for (taskid, taskname) in tasks:
        res.append("    <th>%s</th>" % taskname)
    res.append("    <th>Total</th>")
    res.append("    <th>Hostname<br><font size=-1>"
               "(all builds for system)</font></th>")
    res.append("  </tr>")
    return "\n".join(res)

def format_time(t=None):
    if t == None:
        t = time.time()
    return time.strftime("%Y-%m-%d&nbsp;%H:%M:%S", time.localtime(t))

def latest_content(systems, tasks):
    ctr = {
        'green': 0,
        'yellow': 0,
        'red': 0,
        'white': 0,
        }
    lastbuild = None
    lastplat = None
    res = []
    for bs in systems:
        if lastbuild != bs.buildid:
            pretty = format_time(bs.buildtime)
            age = "%.2f" % ((time.time() - bs.buildtime) / (24*3600))
            res.append('  <tr><td colspan="%d"><a href="%s.html">'
                       '<br>Build %s (%s days ago)'
                       ' %s<br></a>&nbsp;</td></tr>' % (
                           3 + len(tasks), bs.buildid, bs.buildid,
                           age, pretty))
            lastbuild = bs.buildid
            lastplat = bs.sysinfo.os_hw
        if lastplat != bs.sysinfo.os_hw:
            res.append("<tr><td colspan=%d bgcolor=grey></td></tr>" % (
                3 + len(tasks)))
            lastplat = bs.sysinfo.os_hw
        row, row_status = result_row(bs, tasks,
                                     result_details_anchor, system_label,
                                     system_overview_anchor, hostname_label)
        res.append(row)
        ctr[row_status] += 1
    return '\n'.join(res), ctr

def system_label(bs):
    return "%s %s %s" % (
        bs.sysinfo.os_hw, bs.sysinfo.os_rel, bs.sysinfo.testname)

def hostname_label(bs):
    return bs.sysinfo.hostname

def buildid_label(bs):
    return "Build %s" % bs.buildid

def buildtime_label(bs):
    return format_time(bs.buildtime)

def result_details_anchor(bs, label):
    return '    <td><a href="%s/%s_%s/">%s</a></td>' % (
        updatehtml_cfg.filesurl, bs.buildid, bs.sysinfo.systemid, label)

def system_overview_anchor(bs, label):
    return '    <td><a href="%s/sys-%s.html">%s</a></td>' % (
        updatehtml_cfg.overviewurl, bs.sysinfo.systemid, label)

def build_overview_anchor(bs, label):
    return '    <td><a href="%s/build-%s.html">%s</a></td>' % (
        updatehtml_cfg.overviewurl, bs.buildid, label)

def result_row(bs, tasks, leftanchor, leftlabel,
               rightanchor=None, rightlabel=None):
    res = []
    res.append("  <tr>")
    res.append(leftanchor(bs, leftlabel(bs)))

    row_status = "white"

    cursor = _DB.cursor()
    cursor.execute("select task, status, warnings"
                   " from task_result"
                   " where build = %s and system = %s and task in (%s)" % ( 
                       bs.buildid, bs.sysinfo.systemid, ', '.join(
                           ["%s" % task for (task, name) in tasks])))
    m = {}
    for (task, status, warnings) in cursor.fetchall():
        m[task] = (status, warnings)
    cursor.close()

    for (task, taskname) in tasks:
        logtypes = ["log"]
        if not m.has_key(task):
            color = "white"
        else:
            (status, warnings) = m[task]
            if status == "FAIL":
                color = "red"
                logtypes.insert(0, "warn")
                logtypes.insert(0, "fail")
                row_status = "red"
            elif status == "WARN":
                color = "yellow"
                logtypes.insert(0, "warn")
                if row_status == "green" or row_status == "white":
                    row_status = "yellow"
            elif status == "PASS":
                color = "green"
                if row_status == "white":
                    row_status = "green"

        astart = ""
        aend = ""
        for link in logtypes:
            if os.path.exists(os.path.join(updatehtml_cfg.input,
                                           "%s_%s" % (bs.buildid,
                                                      bs.sysinfo.systemid),
                                           taskname + link + ".txt")):
                astart = '<a href="%s/%s_%s/%s%s.txt">' % (
                    updatehtml_cfg.filesurl, bs.buildid, bs.sysinfo.systemid,
                    taskname, link)
                aend = '</a>'
                break
        if astart != "" or color != "white":
            res.append('    <th>%s<img border=0 src="%s%s.gif">%s</th>' % (
                astart, updatehtml_cfg.buttonurl, color, aend))
        else:
            res.append('    <th>&nbsp;</th>')

    res.append('    <th><img border=0 src="%s%s.gif"></th>' % (
        updatehtml_cfg.buttonurl, row_status))

    if rightanchor != None:
        res.append(rightanchor(bs, rightlabel(bs)))

    res.append("  </tr>")
    return '\n'.join(res), row_status

def update_latest():
    systems = get_systems_for_latest()
    tasks = get_all_tasks_for_builds([x.buildid for x in systems])

    (tbl, m) = latest_content(systems, tasks)

    m["project"] = updatehtml_cfg.projectname
    m["now"] = format_time()
    m["buttonurl"] = updatehtml_cfg.buttonurl
    m["heading"] = latest_heading_row(tasks)
    m["content"] = tbl

    page = updatehtml_templates.LATEST_PAGE % m
    open(os.path.join(updatehtml_cfg.output, "latest.html"), "w").write(page)

class task_result:
    def __init__(self, name, status, warnings, time_spent):
        self.name = name
        self.status = status
        self.warnings = warnings
        self.time_spent = time_spent

    def color(self):
        if self.status == "PASS":
            return "green"
        if self.status == "WARN":
            return "yellow"
        if self.status == "FAIL":
            return "red"


def get_task_results(buildid, systemid):
    cursor = _DB.cursor()
    cursor.execute("select t.name, r.status, r.warnings, r.time_spent"
                   " from task_result r, task t"
                   " where r.task = t.id and"
                   "    r.build = %d and r.system = %d"
                   " order by t.sort_order" % (
                       buildid, systemid))
    rows = cursor.fetchall()
    cursor.close()
    return [task_result(*i) for i in list(rows)]

def get_all_task_names():
    cursor = _DB.cursor()
    cursor.execute("select distinct name"
                   " from task"
                   " order by sort_order")
    rows = cursor.fetchall()
    cursor.close()
    return rows

class system:
    def __init__(self, os_hw, os_rel, testname, hostname, systemid):
        self.os_hw = os_hw
        self.os_rel = os_rel
        self.testname = testname
        self.hostname = hostname
        self.systemid = systemid
        

def get_system(systemid):
    cursor = _DB.cursor()
    cursor.execute("select"
                   "     concat(system.sysname, ' ', system.machine),"
                   "     system.release,"
                   "     system.testname,"
                   "     system.name,"
                   "     system.id"
                   " from system"
                   " where system.id = %d" % systemid)
    rows = cursor.fetchall()
    cursor.close()
    return system(*rows[0])

def add_file(tl, files_left, dirname, fn, maxlen):
    if files_left.has_key(fn):
        tl.append(file_listing(dirname, fn, maxlen))
        del files_left[fn]

def mkindex(buildid, systemid, force = 0):

    dirname = os.path.join(updatehtml_cfg.input, "%d_%d" % (buildid, systemid))
    indexname = os.path.join(dirname, "index.html")
    if os.path.isfile(indexname) and not force:
        return 0

    m = {}
    m["project"] = updatehtml_cfg.projectname
    m["now"] = format_time()
    m["buttonurl"] = updatehtml_cfg.fullbuttonurl
    m["overviewurl"] = updatehtml_cfg.overviewurl

    m["buildid"] = buildid
    m["systemid"] = systemid

    # Collect information about the system.
    system = get_system(systemid)
    m["hostname"] = system.hostname
    m["os_hw"] = system.os_hw
    m["os_rel"] = system.os_rel
    m["testname"] = system.testname or "default"

    # Find all files.
    files_left = {}
    for f in os.listdir(dirname):
        files_left[f] = None
    for f in updatehtml_cfg.hidden_files:
        if files_left.has_key(f):
            del files_left[f]
    
    maxlen = max([len(f) for f in files_left])

    tasks = get_task_results(buildid, systemid)

    # Count tasks.
    green = 0
    yellow = 0
    red = 0
    for t in tasks:
        if t.status == "PASS":
            green += 1
        if t.status == "WARN":
            yellow += 1
        if t.status == "FAIL":
            red += 1
    m["green"] = green
    m["yellow"] = yellow
    m["red"] = red

    # Emit task info.
    tl = []
    for t in tasks:
        tl.append('<p><img border=0 src="%s%s.gif"> ' % (
            updatehtml_cfg.fullbuttonurl, t.color()))
        tl.append(t.name)
        tl.append(" %d seconds" % t.time_spent)
        if t.warnings > 0:
            tl.append(" (%d warnings)" % t.warnings)
        tl.append("<pre>")
        for suffix in ["log.txt", "warn.txt", "fail.txt"]:
            add_file(tl, files_left, dirname, t.name + suffix, maxlen)
        for fn in updatehtml_cfg.files_per_task.get(t.name, []):
            add_file(tl, files_left, dirname, fn, maxlen)
        tl.append("</pre>")
            
    m["tasklist"] = ''.join(tl)

    notdone = []
    for (t, ) in get_all_task_names():
        fn = t + "log.txt"
        if files_left.has_key(fn):
            notdone.append('<p><img border=0 src="%swhite.gif"> ' % (
                updatehtml_cfg.fullbuttonurl))
            notdone.append(t)
            notdone.append(' not done:<pre>')
            notdone.append(open(os.path.join(dirname, fn), "r").read())
            notdone.append('</pre>')
            del files_left[fn]
    m["notdone"] = '\n'.join(notdone)

    # list all files not already handled.
    files_left = files_left.keys()
    files_left.sort()
    filelist = []
    for f in files_left:
        filelist.append(file_listing(dirname, f, maxlen))

    m["otherfiles"] = ''.join(filelist)
    page = updatehtml_templates.RESULT_PAGE % m
    open(indexname, "w").write(page)
    return 1

def file_listing(dirname, filename, maxlen):
    st = os.stat(os.path.join(dirname, filename))
    size = st[stat.ST_SIZE]
    tm = format_time(st[stat.ST_MTIME])
    if size != 0:
        abegin = '<a href="%s">' % filename
        aend = '</a>'
    else:
        abegin = aend = ''
    return ('<tt>   %s<img border=0 src="internal-gopher-text" alt="">' 
            ' %s%s %7d bytes   %s</tt><br>' % (
                abegin, filename.ljust(maxlen), aend, size, tm))

def mk_build_overview(buildid):
    pass


def mk_system_overview(systemid):
    cursor = _DB.cursor()
    cursor.execute("select distinct b.id, b.time"
                   " from build b, task_result r"
                   " where b.id = r.build and r.system = %d"
                   " order by b.id desc" % (systemid))
    rows = cursor.fetchall()
    cursor.close()

    sysinfo = get_system(systemid)

    tasks = get_all_tasks_for_system(systemid)

    m = {}
    m["project"] = updatehtml_cfg.projectname
    m["now"] = format_time()
    m["buttonurl"] = updatehtml_cfg.buttonurl
    m["overviewurl"] = updatehtml_cfg.overviewurl

    m["systemid"] = systemid
    m["hostname"] = sysinfo.hostname
    m["os_hw"] = sysinfo.os_hw
    m["os_rel"] = sysinfo.os_rel
    m["testname"] = sysinfo.testname or "default"

    ctr = {
        'green': 0,
        'yellow': 0,
        'red': 0,
        'white': 0,
        }

    res = []
    for (buildid, buildtime) in rows:
        pretty = format_time(buildtime)
        bs = build_sys_info(buildid, buildtime, sysinfo)
        row, row_status = result_row(bs , tasks,
                                     result_details_anchor, buildid_label,
                                     build_overview_anchor, buildtime_label)

        res.append(row)
        ctr[row_status] += 1

    m["content"] = '\n'.join(res)

    res = ["  <tr>",
           "    <th>Build<br><font size=-1>(build details)</font></th>"]
    for (taskid, taskname) in tasks:
        res.append("    <th>%s</th>" % taskname)
    res.append("    <th>Total</th>")
    res.append("    <th>Buildtime<br>"
               "<font size=-1>(all systems for build)</font></th>")
    res.append("  </tr>")
    m["heading"] = "\n".join(res)

    for c in ctr.keys():
        m[c] = ctr[c]

    page = updatehtml_templates.SYS_OVERVIEW_PAGE % m
    fn = os.path.join(updatehtml_cfg.output, "sys-%d.html" % systemid)
    open(fn, "w").write(page)

def mk_all_index():
    cursor = _DB.cursor()
    cursor.execute("select distinct build, system"
                   " from task_result")
    rows = cursor.fetchall()
    cursor.close()
    pending_builds = {}
    pending_systems = {}
    for (buildid, systemid) in rows:
        if mkindex(buildid, systemid, systemid==22):
            print "Generated index for", buildid, systemid
            pending_builds[buildid] = None
            pending_systems[systemid] = None

    for buildid in pending_builds.keys():
        mk_build_overview(buildid)

    for systemid in pending_systems.keys():
        mk_system_overview(systemid)

init()
update_latest()
mk_all_index()
