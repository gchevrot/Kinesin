# USAGE: ./cgenff_charmm2gmx.py DRUG drug.mol2 drug.str charmm36.ff
# Tested with Python 2.7.3. Requires numpy and networkx

# Copyright (C) 2014 E. Prabhu Raman prabhu@outerbanks.umaryland.edu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# <http://www.gnu.org/licenses/>


# EXAMPLE: You have a drug-like molecule in drug.mol2 file
# ParamChem returns a CHARMM stream file drug.str with topology and parameters
# INPUT
# The program needs four inputs:
#   (1) The first argument (resname) is found in the RESI entry in the CHARMM stream file; for example
#       RESI DRUG         0.000  ! here DRUG is the resname
#   (2) drug.mol2 is the .mol2 which you supplied to ParamChem
#   (3) drug.str contains the topology entry and CGenFF parameters that ParamChem generates for you
#   (4) charmm36.ff should contain the CHARMM force-field in GROMACS format
#       Download it from: http://mackerell.umaryland.edu/CHARMM_ff_params.html

# OUTPUT
# The program will generate 4 output files ("DRUG" is converted to lowercase and the files are named accordingly):
#   (1) drug.itp - contains GROMACS itp
#   (2) drug.prm - contains parameters obtained from drug.str which are converted to GROMACS format and units
#   (3) drug.top - A Gromacs topology file which incorporates (1) and (2)
#   (4) drug_ini.pdb - Coordinates of the molecule obtained from drug.mol2

# The program has been tested only on CHARMM stream files containing topology and parameters of a single molecule.

import string
import re
import sys
import os
import numpy as np
import networkx as nx

#=================================================================================================================
def check_versions(str_filename,ffdoc_filename):
    f = open(str_filename, 'r')
    for line in f.readlines():
        if line.startswith("* For use with CGenFF version"):
            entry = re.split('\s+', string.lstrip(line))
            print "--Version of CGenFF detected in ",str_filename,":",entry[6]
    f.close()
    f = open(ffdoc_filename, 'r')
    for line in f.readlines():
        if line.startswith("Parameters taken from CHARMM36 and CGenFF"):
            entry = re.split('\s+', string.lstrip(line))
            print "--Version of CGenFF detected in ",ffdoc_filename,":",entry[6]
    f.close()

#-----------------------------------------------------------------------
def read_gmx_atomtypes(filename):
    atomtypes = []
    f = open(filename, 'r')
    for line in f.readlines():
        if line.startswith(";"):
            continue

        entry = re.split('\s+', string.lstrip(line))
        var = [entry[0],entry[1]]
        atomtypes.append(var)
    f.close()
    return atomtypes
#-----------------------------------------------------------------------
def get_filelist_from_gmx_forcefielditp(ffdir,ffparentfile):
    filelist=[]
    f = open(ffdir+"/"+ffparentfile, 'r')
    for line in f.readlines():
        if line.startswith("#include"):
            entry = re.split('\s+', string.lstrip(line))
            filename = ffdir + "/" + entry[1].replace("\"","")
            filelist.append(filename)
    return filelist
#-----------------------------------------------------------------------
def read_gmx_anglpars(filename):

    angllines = []
    f = open(filename, 'r')
    section="NONE"
    for line in f.readlines():
        if line.startswith(";"):
            continue
        if line.startswith("\n"):
            continue
        if line.startswith("["):
            section="NONE"
        if(section=="ANGL"):
            angllines.append(line)
        if line.startswith("[ angletypes ]"):
            section="ANGL"

    anglpars = []
    anglpar = {}
    for line in angllines:
        entry = re.split('\s+', string.lstrip(line))
	ai, aj, ak, eq = entry[0],entry[1],entry[2],float(entry[4])
        anglpars.append([ai,aj,ak,eq])

    return anglpars
#-----------------------------------------------------------------------
def get_charmm_rtp_lines(filename,molname):
    foundmol=0
    store=0
    rtplines=[]
    f = open(filename, 'r')
    section="NONE"
    for line in f.readlines():
        if(store==1) and line.startswith("RESI"):
            store=0

        if line.startswith("RESI"):
            entry = re.split('\s+', string.lstrip(line))
            rtfmolname=entry[1]
            if(rtfmolname == molname):
                store=1

        if line.startswith("END"):
            store=0

        if(store==1):
            rtplines.append(line)

    return rtplines
#-----------------------------------------------------------------------
def get_charmm_prm_lines(filename):
    foundmol=0
    store=0
    prmlines=[]
    f = open(filename, 'r')
    section="NONE"
    for line in f.readlines():

        if line.startswith("END"):
            section="NONE"
            store=0

        if(store):
            prmlines.append(line)

        if line.startswith("read para"):
            section="PRM"
            store=1


    return prmlines
#-----------------------------------------------------------------------
def parse_charmm_topology(rtplines):
	topology = {}
	noblanks = filter(lambda x: len(x.strip())>0, rtplines)
	nocomments = filter(lambda x: x.strip()[0] not in ['*','!'], noblanks)
	section = "BONDS"	# default
	state = "free"
	for line in nocomments:
		if state == "free":
			if line.find("MASS") == 0:
				if "ATOMS" not in topology.keys():
					topology["ATOMS"] = {}
				s = line.split()
				idx,name,mass,type = int(s[1]),s[2],float(s[3]),s[4]
				if line.find("!"):
					comment = line[line.find("!")+1:].strip()
				else:
					comment = ""
				topology["ATOMS"][name] = [idx,mass,type,comment]
			elif line.find("DECL") == 0:
				if "DECL" not in topology.keys():
					topology["DECL"] = []
				decl = line.split()[1]
				topology["DECL"].append(decl)
			elif line.find("DEFA") == 0:
				topology["DEFA"] = line[4:]
			elif line.find("AUTO") == 0:
				topology["AUTO"] = line[4:]
			elif line.find("RESI") == 0:
				if "RESI" not in topology.keys():
					topology["RESI"] = {}
				state = "resi"
				s = line.split()
				resname, charge = s[1],float(s[2])
				topology["RESI"][resname] = {}
				topology["RESI"][resname]["charge"] = charge
				topology["RESI"][resname]["cmaps"] = []
				topology["RESI"][resname]["bonds"] = []
				topology["RESI"][resname]["impropers"] = []
				topology["RESI"][resname]["double_bonds"] = []
				group = -1 
			elif line.find("PRES") == 0:
				state = "pres"
				s = line.split()
				presname, charge = s[1],float(s[2])
			elif line.find("END") == 0:
				return topology
		elif state == "resi":
			if line.find("RESI")==0:
				state = "resi"
				s = line.split()
				resname, charge = s[1],float(s[2])
				topology["RESI"][resname] = {}
				topology["RESI"][resname]["charge"] = charge
				topology["RESI"][resname]["cmaps"] = []
				topology["RESI"][resname]["bonds"] = []
				topology["RESI"][resname]["impropers"] = []
				topology["RESI"][resname]["double_bonds"] = []
				#topology["RESI"][resname]["groups"] = []
				group = -1 

			elif line.find("GROU")==0:
				group += 1
				topology["RESI"][resname][group] = []
			elif line.find("ATOM")==0: 
				if line.find('!'):
					line = line[:line.find('!')]
				s = line.split()
				name,type,charge = s[1],s[2],float(s[3])
				topology["RESI"][resname][group].append((name,type,charge))
			elif line.find("BOND")==0: 
				if line.find('!'):
					line = line[:line.find('!')]
				s = line.split()
				nbond = (len(s)-1)/2
				for i in range(nbond):
					p,q = s[1+2*i],s[2+2*i]
					topology["RESI"][resname]["bonds"].append((p,q))
			elif line.find("DOUB")==0: 
				if line.find('!'):
					line = line[:line.find('!')]
				s = line.split()
				ndouble = (len(s)-1)/2
				for i in range(ndouble):
					p,q = s[1+2*i],s[2+2*i]
					topology["RESI"][resname]["double_bonds"].append((p,q))
			elif line.find("IMPR")==0: 
				if line.find('!'):
					line = line[:line.find('!')]
				s = line.split()
				nimproper = (len(s)-1)/4
				for i in range(nimproper):
					impr = s[1+4*i],s[2+4*i],s[3+4*i],s[4+4*i]
					topology["RESI"][resname]["impropers"].append(impr)
			elif line.find("CMAP")==0: 
				if line.find('!'):
					line = line[:line.find('!')]
				s = line.split()
				#nimproper = (len(s)-1)/4
				#for i in range(nimproper):
				cmap = s[1:9]
				topology["RESI"][resname]["cmaps"].append(cmap)
			elif line.find("DONOR")==0: 
				continue	# ignore for now
			elif line.find("ACCEPTOR")==0: 
				continue
			elif line.find("IC")==0:
				continue

	return topology
#-----------------------------------------------------------------------
def parse_charmm_parameters(prmlines):

	parameters = {}
	cmapkey = ()
	noblanks = filter(lambda x: len(x.strip())>0, prmlines)
	nocomments = filter(lambda x: x.strip()[0] not in ['*','!'], noblanks)
	section = "ATOM"	# default
	for line in nocomments:
                #print line
		sectionkeys = [ "BOND", "ANGL", "DIHE", \
				"IMPR", "CMAP", "NONB", "HBON", "NBFI" ]
		key = line.split()[0]

                #exit()

		if key[0:4] in sectionkeys:
			section = key[0:4]
			continue

		if section not in parameters.keys():
			parameters[section] = []

                #print line
		if section == "BOND":
			if line.find('!'):
				line = line[:line.find('!')]
			s = line.split()
			ai, aj, kij, rij = s[0],s[1],float(s[2]),float(s[3])
			parameters["BOND"].append((ai,aj,kij,rij))
		elif section == "ANGL":
			if line.find('!'):
				line = line[:line.find('!')]
			s = line.split()
			ai, aj, ak = s[0],s[1],s[2]
			other = map(float,s[3:])
			parameters["ANGL"].append([ai,aj,ak]+other)
		elif section == "DIHE":
			if line.find('!'):
				line = line[:line.find('!')]
			s = line.split()
			ai, aj, ak, al, k, n, d = s[0],s[1],s[2],s[3],float(s[4]),int(s[5]),float(s[6])
			parameters["DIHE"].append([ai,aj,ak,al,k,n,d])
		elif section == "IMPR":
			if line.find('!'):
				line = line[:line.find('!')]
			s = line.split()
			ai, aj, ak, al, k, d = s[0],s[1],s[2],s[3],float(s[4]),float(s[6])
			parameters["IMPR"].append([ai,aj,ak,al,k,d])
		elif section == "CMAP":
			if line.find('!'):
				line = line[:line.find('!')]
			if cmapkey == ():
				s = line.split()
				a,b,c,d,e,f,g,h = s[0:8]
				N = int(s[8])
				cmapkey = (a,b,c,d,e,f,g,h,N)
				cmaplist = []
			else:
				cmapdata = map(float,line.split())
				cmaplist += cmapdata
				if len(cmaplist) == N**2:
					parameters["CMAP"].append([cmapkey,cmaplist])
					cmapkey = ()
		elif section == "NONB":
			if line.find("cutnb")>=0 or line.find("wmin")>=0 or line.find("CUTNB")>=0 or line.find("WMIN")>=0 :
				continue
			bang = line.find('!')
			if bang>0:
				comment = line[bang+1:]
				prm = line[:bang].split()
			else:
				comment = ""
				prm = line.split()
			atname = prm[0]
			epsilon = -float(prm[2])
			half_rmin = float(prm[3])
			parameters["NONB"].append((atname,epsilon,half_rmin))

			if len(prm)>4:
				epsilon14 = -float(prm[5])
				half_rmin14 = float(prm[6])
				if "NONBONDED14" not in parameters.keys():
					parameters["NONBONDED14"] = []
				parameters["NONBONDED14"].append((atname,epsilon14,half_rmin14))


	return parameters
#-----------------------------------------------------------------------
def write_gmx_bon(parameters,header_comments,filename):
        kcal2kJ = 4.18400

	outp = open(filename,"w")
	outp.write("%s\n"%(header_comments))
	outp.write("[ bondtypes ]\n")
	kbond_conversion = 2.0*kcal2kJ/(0.1)**2   	# [kcal/mol]/A**2 -> [kJ/mol]/nm**2
						# factor of 0.5 because charmm bonds are Eb(r)=Kb*(r-r0)**2
	rbond_conversion = .1 			# A -> nm
	outp.write(";%7s %8s %5s %12s %12s\n"%("i","j","func","b0","kb"))
        if(parameters.has_key("BOND")):
	    for p in parameters["BOND"]:
		    ai,aj,kij,rij = p
        	    rij *= rbond_conversion
		    kij *= kbond_conversion
		    outp.write("%8s %8s %5i %12.8f %12.2f\n"%(ai,aj,1,rij,kij))

	kangle_conversion = 2.0*kcal2kJ		# [kcal/mol]/rad**2 -> [kJ/mol]/rad**2
						# factor of 0.5 because charmm angles are Ea(r)=Ka*(a-a0)**2
	kub_conversion = 2.0*kcal2kJ/(0.1)**2   	# [kcal/mol]/A**2 -> [kJ/mol]/nm**2prm
	ub0_conversion = 0.1		   	# A -> nm

	outp.write("\n\n[ angletypes ]\n")
	outp.write(";%7s %8s %8s %5s %12s %12s %12s %12s\n"\
			%("i","j","k","func","theta0","ktheta","ub0","kub"))
        if(parameters.has_key("ANGL")):
            for p in parameters["ANGL"]:
		if len(p) == 5:
		    ai,aj,ak,kijk,theta = p
	            kub = 0.0
		    ub0 = 0.0
		else:
		    ai,aj,ak,kijk,theta,kub,ub0 = p
		
		kijk *= kangle_conversion
		kub *= kub_conversion
		ub0 *= ub0_conversion
		outp.write("%8s %8s %8s %5i %12.6f %12.6f %12.8f %12.2f\n"\
				%(ai,aj,ak,5,theta,kijk,ub0,kub))

	kdihe_conversion = kcal2kJ
	outp.write("\n\n[ dihedraltypes ]\n")
	outp.write(";%7s %8s %8s %8s %5s %12s %12s %5s\n"\
			%("i","j","k","l","func","phi0","kphi","mult"))
	#parameters["DIHEDRALS"].sort(demote_wildcards)
        if(parameters.has_key("DIHE")):
	    for p in parameters["DIHE"]:
		ai,aj,ak,al,k,n,d = p
		k *= kdihe_conversion
		outp.write("%8s %8s %8s %8s %5i %12.6f %12.6f %5i\n"\
				%(ai,aj,ak,al,9,d,k,n))

	kimpr_conversion = kcal2kJ*2	# see above
	outp.write("\n\n[ dihedraltypes ]\n")
	outp.write("; 'improper' dihedrals \n")
	outp.write(";%7s %8s %8s %8s %5s %12s %12s\n"\
			%("i","j","k","l","func","phi0","kphi"))
        if(parameters.has_key("IMPR")):
	#parameters["IMPROPERS"].sort(demote_wildcards)
    	    for p in parameters["IMPR"]:
		ai,aj,ak,al,k,d = p
		k *= kimpr_conversion
		outp.write("%8s %8s %8s %8s %5i %12.6f %12.6f\n"\
				%(ai,aj,ak,al,2,d,k))



	outp.close()
	return
#-----------------------------------------------------------------------
def write_gmx_mol_top(filename,ffdir,prmfile,itpfile,molname):
        outp = open(filename,"w")
	outp.write("#include \"%s/forcefield.itp\"\n" % (ffdir))
        outp.write("\n")
        outp.write("; additional params for the molecule\n")
	outp.write("#include \"%s\"\n" % (prmfile))
        outp.write("\n")
	outp.write("#include \"%s\"\n" % (itpfile))
        outp.write("\n")
	outp.write("#include \"%s/tip3p.itp\"\n" % (ffdir))
        outp.write("#ifdef POSRES_WATER\n")
        outp.write("; Position restraint for each water oxygen\n")
        outp.write("[ position_restraints ]\n")
        outp.write(";  i funct       fcx        fcy        fcz\n")
        outp.write("   1    1       1000       1000       1000\n")
        outp.write("#endif\n")
        outp.write("\n")
        outp.write("; Include topology for ions\n")
	outp.write("#include \"%s/ions.itp\"\n" % (ffdir))
        outp.write("\n")
        outp.write("[ system ]\n")
        outp.write("; Name\n")
        outp.write("mol\n")
        outp.write("\n")
        outp.write("[ molecules ]\n")
        outp.write("; Compound        #mols\n")
	outp.write("%s          1\n" % (molname))
        outp.write("\n")

        outp.close()
#=================================================================================================================
class atomgroup:
    """
    A class that contains the data structures and functions to store and process
    data related to groups of atoms (read molecules)

    USAGE: m = atomgroup()
    """

    #TODO, remove this molcount, it is not useful and is confusing
    molcount=0  #counts the number of molecules in the group

    def __init__(self):
        self.molcount = self.molcount+1 #TODO
        self.G = nx.Graph()
        self.name = ""
        self.natoms = 0
        self.nbonds = 0
        self.angles = []
        self.nangles = 0
        self.dihedrals = []
        self.ndihedrals = 0
        self.impropers = []
        self.nimpropers = 0
        #self.coord=np.zeros((self.natoms,3),dtype=float)

    #-----------------------------------------------------------------------
    def read_charmm_rtp(self,rtplines,atomtypes):
        """
        Reads CHARMM rtp
        Reads atoms, bonds, impropers
        Stores connectivity as a graph
        Autogenerates angles and dihedrals

        USAGE: m = atomgroup() ; m.read_charmm_rtp(rtplines,atomtypes)

        """
        #initialize everything
        self.G = nx.Graph()
        self.name = ""
        self.natoms = 0
        self.nbonds = 0
        self.angles = []
        self.nangles = 0
        self.dihedrals = []
        self.ndihedrals = 0
        self.impropers = []
        self.nimpropers = 0

        atm = {}

        for line in rtplines:
	    if line.find('!'):
	        line = line[:line.find('!')]

            if line.startswith("RESI"):
                entry = re.split('\s+', string.lstrip(line))
                self.name=entry[1]

            if line.startswith("ATOM"):
                entry = re.split('\s+', string.lstrip(line))
                atm[self.natoms] = {'type':entry[2], 'resname':self.name, 'name':entry[1],
                      'charge':float(entry[3]),'mass':float(0.00), 'beta':float(0.0),
                        'x':float(9999.9999),'y':float(9999.9999),'z':float(9999.9999),'segid':self.name, 'resid':'1' }

                for typei in atomtypes:
                    if(typei[0] == atm[self.natoms]['type']):
                        atm[self.natoms]['mass'] = float(typei[1])
                        break

                self.G.add_node(self.natoms, atm[self.natoms])
                self.natoms=self.natoms+1

            if line.startswith("BOND") or line.startswith("DOUB"):
                entry = re.split('\s+', string.rstrip(string.lstrip(line)))
                numbonds = int((len(entry)-1)/2)
                for bondi in range(0,numbonds):
                    found1 = False
                    found2 = False
                    for i in range(0,self.natoms):
                        if(atm[i]['name'] == entry[(bondi*2)+1]):
                            found1 = True
                            break
                    for j in range(0,self.natoms):
                        if(atm[j]['name'] == entry[(bondi*2)+2]):
                            found2 = True
                            break
                    if(not found1):
                        print "Error:atomgroup:read_charmm_rtp> Atomname not found in top",entry[(bondi*2)+1]
                    if(not found2):
                        print "Error:atomgroup:read_charmm_rtp> Atomname not found in top",entry[(bondi*2)+2]
                    self.G.add_edge(i,j)
                    self.G[i][j]['order']='1' # treat all bonds as single for now
                    self.nbonds=self.nbonds+1

            if line.startswith("IMP"):
                entry = re.split('\s+', string.lstrip(line))
                numimpr = int((len(entry)-2)/4)
                for impi in range(0,numimpr):
                    for i in range(0,self.natoms):
                        if(atm[i]['name'] == entry[(impi*4)+1]):
                            break
                    for j in range(0,self.natoms):
                        if(atm[j]['name'] == entry[(impi*4)+2]):
                            break
                    for k in range(0,self.natoms):
                        if(atm[k]['name'] == entry[(impi*4)+3]):
                            break
                    for l in range(0,self.natoms):
                        if(atm[l]['name'] == entry[(impi*4)+4]):
                            break
                    var = [i,j,k,l]
                    self.impropers.append(var)

        self.nimpropers = len(self.impropers)
        if(self.ndihedrals > 0 or self.nangles > 0):
            print "WARNING:atomgroup:read_charmm_rtp> Autogenerating angl-dihe even though they are preexisting",self.nangles,self.ndihedrals
        self.autogen_angl_dihe()
        self.coord = np.zeros((self.natoms,3),dtype=float)
#-----------------------------------------------------------------------
    def autogen_angl_dihe(self):
        self.angles = []
        for atomi in range(0,self.natoms):
            nblist = []
            for nb in self.G.neighbors(atomi):
                nblist.append(nb)
            for i in range(0,len(nblist)-1):
                for j in range(i+1,len(nblist)):
                    var = [nblist[i],atomi,nblist[j]]
                    self.angles.append(var)
        self.nangles = len(self.angles)
        self.dihedrals = []
        for i,j in self.G.edges_iter():
            nblist1 = []
            for nb in self.G.neighbors(i):
                if(nb != j):
                    nblist1.append(nb)
            nblist2 = []
            for nb in self.G.neighbors(j):
                if(nb != i):
                    nblist2.append(nb)
            if(len(nblist1) > 0 and len(nblist2) > 0 ):
                for ii in range(0,len(nblist1)):
                    for jj in range(0,len(nblist2)):
                        var = [nblist1[ii],i,j,nblist2[jj]]
                        if(var[0] != var[3]):
                            self.dihedrals.append(var)
        self.ndihedrals = len(self.dihedrals)
#-----------------------------------------------------------------------
    def get_nonplanar_dihedrals(self,angl_params):
        nonplanar_dihedrals=[]
        cutoff=179.9
        for var in self.dihedrals:
            d1=self.G.node[var[0]]['type']            
            d2=self.G.node[var[1]]['type']
            d3=self.G.node[var[2]]['type']
            d4=self.G.node[var[3]]['type']
            keep=1
            for angl_param in angl_params:
                p1=angl_param[0]
                p2=angl_param[1]
                p3=angl_param[2]
                eq=angl_param[3]
                if( d2==p2 and ( ( d1==p1 and d3==p3) or (d1==p3 and d3==p1))):
                    if(eq > cutoff):
                        keep=-1
                        break
                if( d3==p2 and ( (d2==p1 and d4==p3) or (d2==p3 and d4==p1))):
                    if(eq > cutoff):
                        keep=-1
                        break

                 
            if(keep==1):
                nonplanar_dihedrals.append(var)

        return nonplanar_dihedrals
#-----------------------------------------------------------------------
    def write_gmx_itp(self,filename,angl_params):
        f = open(filename, 'w')
        f.write("; Created by cgenff_charmm2gmx.py\n")
        f.write("\n")
        f.write("[ moleculetype ]\n")
        f.write("; Name            nrexcl\n")
        f.write("%s              3\n" % self.name)
        f.write("\n")
        f.write("[ atoms ]\n")
        f.write(";   nr       type  resnr residue  atom   cgnr     charge       mass  typeB    chargeB      massB\n")
        f.write("; residue   1 %s rtp %s q  qsum\n" % (self.name,self.name))
        pairs14 = nx.Graph()
        for atomi in range(0,self.natoms):
            pairs14.add_node(atomi)
            f.write("%6d %10s %6s %6s %6s %6d %10.3f %10.3f   ;\n" % 
               ( atomi+1,self.G.node[atomi]['type'],
               self.G.node[atomi]['resid'],self.name,self.G.node[atomi]['name'],atomi+1,
               self.G.node[atomi]['charge'],self.G.node[atomi]['mass'] ) )
        f.write("\n")
        f.write("[ bonds ]\n")
        f.write(";  ai    aj funct            c0            c1            c2            c3\n")
        for i,j in self.G.edges_iter():
            f.write("%5d %5d     1\n" % (i+1,j+1) )
        f.write("\n")
        f.write("[ pairs ]\n")
        f.write(";  ai    aj funct            c0            c1            c2            c3\n")
        for var in self.dihedrals:
            if (len(nx.dijkstra_path(self.G,var[0],var[3])) == 4): #this is to remove 1-2 and 1-3 included in dihedrals of rings
                pairs14.add_edge(var[0],var[3])
        for i,j in pairs14.edges_iter():
            f.write("%5d %5d     1\n" % (i+1,j+1) )
        f.write("\n")
        f.write("[ angles ]\n")
        f.write(";  ai    aj    ak funct            c0            c1            c2            c3\n")
        for var in self.angles:
            f.write("%5d %5d %5d    5\n" % (var[0]+1,var[1]+1,var[2]+1) )
        f.write("\n")
        f.write("[ dihedrals ]\n")
        f.write(";  ai    aj    ak    al funct            c0            c1            c2            c3            c4            c5\n")
        nonplanar_dihedrals=self.get_nonplanar_dihedrals(angl_params)
        for var in nonplanar_dihedrals:
            f.write("%5d %5d %5d %5d     9\n" % (var[0]+1,var[1]+1,var[2]+1,var[3]+1) )
        f.write("\n")
        if(self.nimpropers > 0):
            f.write("[ dihedrals ]\n")
            f.write(";  ai    aj    ak    al funct            c0            c1            c2            c3\n")
            for var in self.impropers:
                f.write("%5d %5d %5d %5d     2\n" % (var[0]+1,var[1]+1,var[2]+1,var[3]+1) )
            f.write("\n")
        f.close()

#-----------------------------------------------------------------------
    def read_mol2_coor_only(self,filename):
        check_natoms = 0
        check_nbonds = 0
        f = open(filename, 'r')
        atm = {}
        section="NONE"
        for line in f.readlines():
            secflag=False
            if line.startswith("@"):
                secflag=True
                section="NONE"


            if((section=="NATO") and (not secflag)):
                entry = re.split('\s+', string.lstrip(line))
                check_natoms=int(entry[0])
                check_nbonds=int(entry[1])
                if(check_natoms != self.natoms):
                    print "error in atomgroup.py: read_mol2_coor_only: natoms in mol2 .ne. top"
                    print check_natoms,self.natoms
                    exit()
                if(check_nbonds != self.nbonds):
                    print "error in atomgroup.py: read_mol2_coor_only: nbonds in mol2 .ne. top"
                    print check_nbonds,self.nbonds
                    exit()

                section="NONE"  

            if((section=="MOLE") and (not secflag)):
                self.name=line.strip()
                section="NATO" #next line after @<TRIPOS>MOLECULE contains atom, bond numbers

            if((section=="ATOM") and (not secflag)):
                entry = re.split('\s+', string.lstrip(line))
                atomi = int(entry[0])-1
                self.G.node[atomi]['x'] = float(entry[2])
                self.G.node[atomi]['y'] = float(entry[3])
                self.G.node[atomi]['z'] = float(entry[4])
                self.coord[atomi][0] = float(entry[2])
                self.coord[atomi][1] = float(entry[3])
                self.coord[atomi][2] = float(entry[4])

            if line.startswith("@<TRIPOS>MOLECULE"):
                section="MOLE"
            if line.startswith("@<TRIPOS>ATOM"):
                section="ATOM"
            if line.startswith("@<TRIPOS>BOND"):
                section="BOND"
#-----------------------------------------------------------------------
    def write_pdb(self,f):
        for atomi in range(0,self.natoms):
            if(len(self.G.node[atomi]['name']) > 4):
                print "error in atomgroup.write_pdb(): atom name >  characters"
                exit()

            if(len(self.G.node[atomi]['name']) == 4):
                f.write("ATOM  %5d %-4.4s %-4.4s %4s    %8.3f%8.3f%8.3f%6.2f%6.2f\n" %
                (atomi+1,self.G.node[atomi]['name'],self.name,self.G.node[atomi]['resid'],self.coord[atomi][0],
                self.coord[atomi][1],self.coord[atomi][2],1.0,self.G.node[atomi]['beta']))
            else:
                f.write("ATOM  %5d  %-4.4s%-4.4s %4s    %8.3f%8.3f%8.3f%6.2f%6.2f\n" %
                (atomi+1,self.G.node[atomi]['name'],self.name,self.G.node[atomi]['resid'],self.coord[atomi][0],
                self.coord[atomi][1],self.coord[atomi][2],1.0,self.G.node[atomi]['beta']))
        f.write("END\n")

#=================================================================================================================


if(len(sys.argv) != 5):
    print "Usage: RESNAME drug.mol2 drug.str charmm36.ff"
    exit()

mol_name = sys.argv[1]
mol2_name = sys.argv[2]
rtp_name = sys.argv[3]
ffdir = sys.argv[4]
atomtypes_filename = ffdir + "/atomtypes.atp"

print "NOTE1: Code tested with python 2.7.3. Your version:",sys.version
print ""
print "NOTE2: Please be sure to use the same version of CGenFF in your simulations that was used during parameter generation:"
check_versions(rtp_name,ffdir + "/forcefield.doc")
print ""
print "NOTE3: In order to avoid duplicated parameters, do NOT select the 'Include parameters that are already in CGenFF' option when uploading a molecule into CGenFF."


#for output
itpfile = mol_name.lower() + ".itp"
prmfile = mol_name.lower() + ".prm"
initpdbfile = mol_name.lower() + "_ini.pdb"
topfile = mol_name.lower() +".top"

atomtypes = read_gmx_atomtypes(atomtypes_filename)

angl_params = []  #needed for detecting triple bonds
filelist = get_filelist_from_gmx_forcefielditp(ffdir,"forcefield.itp")
for filename in filelist:
    anglpars = read_gmx_anglpars(filename)
    angl_params = angl_params + anglpars


m = atomgroup()
rtplines=get_charmm_rtp_lines(rtp_name,mol_name)
m.read_charmm_rtp(rtplines,atomtypes)


m.read_mol2_coor_only(mol2_name)
f = open(initpdbfile, 'w')
m.write_pdb(f)
f.close()


prmlines=get_charmm_prm_lines(rtp_name)
params = parse_charmm_parameters(prmlines)
write_gmx_bon(params,"",prmfile)
anglpars = read_gmx_anglpars(prmfile)
angl_params = angl_params + anglpars # append the new angl params


m.write_gmx_itp(itpfile,angl_params)
write_gmx_mol_top(topfile,ffdir,prmfile,itpfile,mol_name)

exit()

