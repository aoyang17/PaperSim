import com.comsol.model.*;
import com.comsol.model.util.*;
import java.util.Arrays;

/*__PAPERSIM_REPORT__*/
/** Build only: radial cylinder, material CH, finite-strain SVK, exact J2 NCP.
 * No solve call is permitted here. Run the saved MPH independently with batch.
 */
public final class __CLASS_NAME__ {
  private static Model m;
  private static void par(String n, String e, String d) { m.param().set(n,e,d); }
  private static String vdesc(String n) {
    switch (n) {
      case "rho": return "normalized radial coordinate R/A";
      case "r_current": return "current radial coordinate in the deformed configuration";
      case "fr": return "radial total stretch";
      case "ft": return "hoop total stretch";
      case "fz": return "homogeneous axial total stretch";
      case "fer": return "radial elastic stretch";
      case "fet": return "hoop elastic stretch";
      case "fez": return "axial elastic stretch";
      case "fpr": return "radial plastic stretch";
      case "fpt": return "hoop plastic stretch";
      case "fpz": return "axial plastic stretch";
      case "achem": return "concentration-dependent chemical deformation stretch";
      case "Jtot": return "total deformation Jacobian";
      case "detFp": return "plastic deformation Jacobian";
      case "eer": return "radial elastic Green-Lagrange strain";
      case "eet": return "hoop elastic Green-Lagrange strain";
      case "eez": return "axial elastic Green-Lagrange strain";
      case "E0": return "Young modulus interpolation endpoint";
      case "E1": return "fully lithiated Young modulus interpolation endpoint";
      case "nuc": return "concentration-dependent Poisson ratio";
      case "G": return "concentration-dependent shear modulus";
      case "lamel": return "concentration-dependent first Lame parameter";
      case "W": return "reference elastic energy density";
      case "taur": return "radial Kirchhoff stress";
      case "taut": return "hoop Kirchhoff stress";
      case "tauz": return "axial Kirchhoff stress";
      case "taum": return "hydrostatic Kirchhoff stress";
      case "taueq": return "von Mises equivalent Kirchhoff stress";
      case "tauden": return "regularized equivalent stress denominator";
      case "devr": return "radial deviatoric Kirchhoff stress";
      case "devt": return "hoop deviatoric Kirchhoff stress";
      case "devz": return "axial deviatoric Kirchhoff stress";
      case "Pr": return "radial first Piola-Kirchhoff stress";
      case "Pt": return "hoop first Piola-Kirchhoff stress";
      case "Pz": return "axial first Piola-Kirchhoff stress";
      case "sigr": return "radial Cauchy stress";
      case "sigt": return "hoop Cauchy stress";
      case "sigz": return "axial Cauchy stress";
      case "sigvm": return "von Mises Cauchy stress";
      case "paper_proxy": return "paper stress proxy absolute radial-minus-hoop Cauchy stress";
      case "yieldgap": return "yield function gap including hardening";
      case "ncp": return "exact nonlinear complementarity residual for plastic multiplier";
      case "mobility": return "concentration-dependent Cahn-Hilliard mobility";
      case "fchemprime": return "derivative of chemical free energy";
      case "mu_el": return "elastic contribution to chemical potential";
      case "dG": return "derivative of shear modulus with respect to concentration";
      case "dlamel": return "derivative of first Lame parameter with respect to concentration";
      case "dE": return "derivative of Young modulus with respect to concentration";
      case "dnu": return "derivative of Poisson ratio with respect to concentration";
      case "dennu": return "denominator helper for concentration-dependent elastic constants";
      case "Ec": return "chemical elastic strain measure";
      case "phi": return "chemical free energy contribution";
      case "tau2": return "second invariant helper for plastic power";
      case "plastic_power": return "plastic dissipation rate";
      case "Qrad": return "radial integration weight";
      case "sstart": return "smooth boundary startup factor";
      case "creservoir": return "prescribed surface lithium concentration";
      case "Fchem": return "chemical contribution to total free energy";
      case "Fgrad": return "gradient-energy contribution";
      default: return "paper constitutive intermediate " + n;
    }
  }
  private static void v(String n, String e) { m.component("c1").variable("constitutive").set(n,e,vdesc(n)); }
  private static void field(String n, String init, boolean local) {
    String tag="d_"+n;
    m.component("c1").common().create(tag,"DependentVariableField");
    m.component("c1").common(tag).selection().named("sel_domain");
    m.component("c1").common(tag).set("fieldType","scalar");
    m.component("c1").common(tag).set("name",n);
    m.component("c1").common(tag).set("components",new String[]{n});
    m.component("c1").common(tag).set("unit","1");
    m.component("c1").common(tag).set("quantity","dimensionless");
    m.component("c1").common(tag).set("shapeFunctionType",local?"shdisc":"shlag");
    m.component("c1").common(tag).set("elementOrder","1");
    m.component("c1").common(tag).set("initialValue",init);
    m.component("c1").common(tag).set("initialTimeDerivative","0");
  }
  private static void weak(String tag, String expression) {
    m.component("c1").common().create(tag,"WeakContribution");
    m.component("c1").common(tag).selection().named("sel_domain");
    m.component("c1").common(tag).set("weakExpression",expression);
    // Two Gauss points: DG1 history unknowns enforce local NCP at these points.
    m.component("c1").common(tag).set("integrationOrder","2");
  }
  private static void constraint(String tag,String selection,String expression) {
    m.component("c1").common().create(tag,"Constraint");
    m.component("c1").common(tag).selection().named(selection);
    m.component("c1").common(tag).set("constraint",expression);
    // Symmetric reaction for chat acts ONLY on the chat test/evolution row.
    // It does not replace the independent mu row or impose zero influx.
  }
  public static Model run() throws Exception {
    m=ModelUtil.create("__CLASS_NAME__");
    m.label("Chen2014 pilot 0-24.5 s: finite strain CH + history J2, free axial resultant");
    m.component().create("c1",true);
    par("A","70[nm]","Initial cylinder radius");
    par("S","0.915[GPa]","Paper chemical energy/stress scale");
    par("Dli","2e-17[m^2/s]","Paper diffusivity; mobility Dli*c*(1-c)/S");
    par("kappa","2e-9[J/m]","Reference gradient energy coefficient");
    par("Omix","2.6","Regular-solution interaction parameter");
    par("beta","0.5874","Chemical stretch endpoint increment");
    par("c0","1e-4","Disclosed initial concentration regularization");
    par("cbeta","0.872","Printed reservoir boundary concentration, not 3.75/4.4");
    par("E0","160[GPa]","Young modulus at c=0");
    par("E1","40[GPa]","Young modulus at c=1");
    par("nu0","0.24","Poisson ratio at c=0");
    par("nu1","0.22","Poisson ratio at c=1");
    par("sy0","1.5[GPa]","Kirchhoff J2 initial yield strength");
    par("Hiso","1[GPa]","Linear isotropic hardening modulus");
    par("tref","2.45[s]","Rate-unit scaling only; not viscosity");
    par("tramp","0.245[s]","Disclosed smooth boundary startup");
    par("tfinal","24.5[s]","Authorized pilot end; no full-paper solve");
    par("dtout","0.245[s]","Pilot output interval");
    par("dtmax","0.245[s]","Maximum actual BDF step");
    par("dtinit","0.00245[s]","Initial BDF step suggestion");
    par("Nelem","280","Uniform radial line elements; h=0.25nm");
    par("tau_floor","1e-12*S","Denominator safeguard only, no yield smoothing");
    m.component("c1").geom().create("g1",1);
    m.component("c1").geom("g1").lengthUnit("m");
    m.component("c1").geom("g1").create("i1","Interval");
    m.component("c1").geom("g1").feature("i1").set("p1","0");
    m.component("c1").geom("g1").feature("i1").set("p2","A");
    m.component("c1").geom("g1").run();
    m.component("c1").selection().create("sel_domain","Explicit");
    m.component("c1").selection("sel_domain").geom("g1",1);
    m.component("c1").selection("sel_domain").all();
    for(String tag:new String[]{"sel_axis","sel_outer"}) {
      m.component("c1").selection().create(tag,"Box");
      m.component("c1").selection(tag).geom("g1",0);
      m.component("c1").selection(tag).set("entitydim",0);
      m.component("c1").selection(tag).set("xmin",tag.equals("sel_axis")?"-A*1e-8":"A*(1-1e-8)");
      m.component("c1").selection(tag).set("xmax",tag.equals("sel_axis")?"A*1e-8":"A*(1+1e-8)");
    }
    for(String[] op:new String[][]{{"intop1","Integration"},{"minop1","Minimum"},{"maxop1","Maximum"}}) {
      m.component("c1").cpl().create(op[0],op[1]);
      m.component("c1").cpl(op[0]).selection().named("sel_domain");
      m.component("c1").cpl(op[0]).set("intorder","2");
      if(!op[0].equals("intop1")) m.component("c1").cpl(op[0]).set("points","integration");
    }
    m.component("c1").variable().create("constitutive");
    m.component("c1").variable("constitutive").selection().named("sel_domain");
    v("rho","x/A");
    v("r_current","x+A*ur");
    v("fr","1+A*urx");
    v("ft","if(x>A*1e-12,1+A*ur/x,fr)");
    v("fz","Lam");
    v("achem","1+beta*(chat-c0)/(1-c0)");
    v("hc","beta/((1-c0)*achem)");
    v("fpr","exp(lr)"); v("fpt","exp(lt)"); v("fpz","exp(-lr-lt)");
    v("detFp","fpr*fpt*fpz");
    v("fer","fr/(achem*fpr)"); v("fet","ft/(achem*fpt)"); v("fez","fz/(achem*fpz)");
    v("eer","(fer^2-1)/2"); v("eet","(fet^2-1)/2"); v("eez","(fez^2-1)/2");
    v("etr","eer+eet+eez"); v("ee2","eer^2+eet^2+eez^2");
    v("Ec","E0+(E1-E0)*chat"); v("nuc","nu0+(nu1-nu0)*chat");
    v("dE","E1-E0"); v("dnu","nu1-nu0");
    v("G","Ec/(2*(1+nuc))");
    v("lamel","Ec*nuc/((1+nuc)*(1-2*nuc))");
    v("dG","dE/(2*(1+nuc))-Ec*dnu/(2*(1+nuc)^2)");
    v("dennu","(1+nuc)*(1-2*nuc)");
    v("dlamel","dE*nuc/dennu+Ec*dnu*(1+2*nuc^2)/dennu^2");
    v("W","achem^3*(G*ee2+lamel*etr^2/2)");
    v("taur","achem^3*fer^2*(2*G*eer+lamel*etr)");
    v("taut","achem^3*fet^2*(2*G*eet+lamel*etr)");
    v("tauz","achem^3*fez^2*(2*G*eez+lamel*etr)");
    v("taum","(taur+taut+tauz)/3");
    v("devr","taur-taum"); v("devt","taut-taum"); v("devz","tauz-taum");
    v("tau2","1.5*(devr^2+devt^2+devz^2)");
    v("taueq","if(tau2>0[Pa^2],sqrt(tau2),0[Pa])");
    v("tauden","max(taueq,tau_floor)");
    v("Pr","taur/fr"); v("Pt","taut/ft"); v("Pz","tauz/fz");
    v("Jtot","fr*ft*fz");
    v("sigr","taur/Jtot"); v("sigt","taut/Jtot"); v("sigz","tauz/Jtot");
    v("sigvm","taueq/Jtot"); v("paper_proxy","abs(sigr-sigt)");
    v("yieldgap","(sy0+Hiso*qp-taueq)/S");
    v("ncp","eta-max(0,eta-yieldgap)");
    v("plastic_power","taueq*eta/tref");
    v("mu_el","hc*(3*W-taur-taut-tauz)+achem^3*(dG*ee2+dlamel*etr^2/2)");
    // No concentration clipping: a trajectory leaving (0,1) must fail visibly.
    v("fchemprime","log(chat/(1-chat))+Omix*(1-2*chat)");
    v("mobility","Dli*chat*(1-chat)/S");
    v("Qrad","-Dli*chat*(1-chat)*muhatx");
    v("Fchem","S*(chat*log(chat)+(1-chat)*log(1-chat)+Omix*chat*(1-chat))");
    v("Fgrad","kappa*chatx^2/2");
    v("sstart","min(1,max(0,t/tramp))");
    v("creservoir","c0+(cbeta-c0)*(3*sstart^2-2*sstart^3)");
    field("chat","c0",false);
    field("muhat","log(c0/(1-c0))+Omix*(1-2*c0)",false);
    field("ur","0",false);
    for(String n:new String[]{"lr","lt","qp","eta"}) field(n,"0",true);
    // API fix03: COMSOL6.2 common initialValue metadata did not initialize DOFs.
    // Low-level model.init() was verified by initialization-only job7935764.
    m.init().create("explicit_initial_fields");
    m.init("explicit_initial_fields").selection().named("sel_domain");
    m.init("explicit_initial_fields").set("c1.chat","c0");
    m.init("explicit_initial_fields").set("c1.muhat","log(c0/(1-c0))+Omix*(1-2*c0)");
    for(String n:new String[]{"ur","lr","lt","qp","eta"}) m.init("explicit_initial_fields").set("c1."+n,"0");
    weak("w_chat","rho*(tref*d(chat,t)*test(chat)+tref*Dli*chat*(1-chat)*muhatx*test(chatx))");
    weak("w_mu","rho*((muhat-fchemprime-mu_el/S)*test(muhat)-(kappa/S)*chatx*test(muhatx))");
    weak("w_radial","rho*A*(Pr/S)*test(urx)+(Pt/S)*test(ur)");
    weak("w_lr","rho*(tref*d(lr,t)-1.5*eta*devr/tauden)*test(lr)");
    weak("w_lt","rho*(tref*d(lt,t)-1.5*eta*devt/tauden)*test(lt)");
    weak("w_qp","rho*(tref*d(qp,t)-eta)*test(qp)");
    weak("w_ncp","rho*ncp*test(eta)");
    constraint("axis_ur","sel_axis","ur");
    constraint("reservoir_chat","sel_outer","chat-creservoir");
    m.component("c1").physics().create("ge","GlobalEquations");
    m.component("c1").physics("ge").feature("ge1").set("name",new String[]{"Lam"});
    m.component("c1").physics("ge").feature("ge1").set("equation",new String[]{"intop1(rho*Pz/S)/A"});
    m.component("c1").physics("ge").feature("ge1").set("initialValueU",new String[]{"1"});
    m.component("c1").physics("ge").feature("ge1").set("initialValueUt",new String[]{"0"});
    m.component("c1").mesh().create("mesh1","g1");
    m.component("c1").mesh("mesh1").create("edg1","Edge");
    m.component("c1").mesh("mesh1").feature("edg1").create("dis1","Distribution");
    m.component("c1").mesh("mesh1").feature("edg1").feature("dis1").set("numelem","Nelem");
    m.component("c1").mesh("mesh1").run();
    String times="range(0,0.0245,0.245) range(0.49,0.245,24.5)";
    m.study().create("std1");
    m.study("std1").create("time","Transient");
    m.study("std1").feature("time").set("tlist",times);
    m.study("std1").createAutoSequences("sol");
    m.sol("sol1").feature("v1").set("scalemethod","manual");
    m.sol("sol1").feature("v1").set("scaleval",1.0);
    m.sol("sol1").feature("t1").set("tlist",times);
    m.sol("sol1").feature("t1").set("timemethod","bdf");
    m.sol("sol1").feature("t1").set("maxorder",1);
    m.sol("sol1").feature("t1").set("rtol",1e-4);
    m.sol("sol1").feature("t1").set("atolglobalvaluemethod","manual");
    m.sol("sol1").feature("t1").set("atolglobalmethod","unscaled");
    m.sol("sol1").feature("t1").set("atolglobal","1e-7");
    // API fix02: omit per-field overrides; actual 6.2 build rejected both forms.
    // All fields now use unscaled atol 1e-7, stricter than muhat's 1e-6 ceiling.
    m.sol("sol1").feature("t1").set("tstepsbdf","strict");
    m.sol("sol1").feature("t1").set("maxstepconstraintbdf","const");
    m.sol("sol1").feature("t1").set("maxstepbdf","dtmax");
    m.sol("sol1").feature("t1").set("initialstepbdfactive",true);
    m.sol("sol1").feature("t1").set("initialstepbdf","dtinit");
    m.sol("sol1").feature("t1").feature("fc1").set("maxiter",40);
    // Cycle3: joint DAE error-control/Jacobian and complete output adjustment.
    // Exact NCP, initial state, damping, tolerances and step limits unchanged.
    m.sol("sol1").feature("t1").set("estrat","exclude");
    m.sol("sol1").feature("t1").set("masssingular","yes");
    m.sol("sol1").feature("t1").feature("fc1").set("jtech","onevery");
    m.sol("sol1").feature("t1").set("tout","tsteps");
    m.sol("sol1").feature("t1").set("tstepsstore",1);
    m.sol("sol1").feature("t1").set("reacf","on");
    m.sol("sol1").feature("t1").set("storeudot","on");
    m.result().dataset().create("dsetpilot","Solution");
    m.result().dataset("dsetpilot").set("solution","sol1");
    m.result().create("pgc","PlotGroup1D");
    m.result("pgc").set("data","dsetpilot");
    m.result("pgc").create("line1","LineGraph");
    m.result("pgc").feature("line1").selection().named("sel_domain");
    m.result("pgc").feature("line1").set("expr","chat");
    m.save("__OUTPUT_MPH__");
    System.out.println("CHEN_PAPERSIM_BUILD_ONLY_OK file=__OUTPUT_MPH__");
    System.out.println("FIELDS="+Arrays.toString(m.component("c1").common().tags()));
    System.out.println("STUDY=std1 SOLVER=sol1 TFINAL_SECONDS=24.5 ELEMENTS=280");
    System.out.println("PHYSICS=full_mu_el; finite_strain; exact_J2_NCP; history_lr_lt_qp; zero_axial_resultant");
    return m;
  }
  public static void main(String[] args) throws Exception { run(); }
}
