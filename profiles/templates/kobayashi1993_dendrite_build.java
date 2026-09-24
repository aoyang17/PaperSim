/** PaperSim generated contract. */
/*__GENERATED_HEADER__*/

import com.comsol.model.*;
import com.comsol.model.util.*;

/**
 * Kobayashi 1993, Physica D 63 (1993), Eqs. (3)-(5), written in the
 * PaperSim comsol-modeling style.
 *
 * Reading order:
 *   1. parameter table;
 *   2. variable table, split by physical layer;
 *   3. geometry and named domain selection;
 *   4. two conservative General Form PDE interfaces, one per dependent field;
 *   5. initial conditions;
 *   6. mesh, study, and solver settings;
 *   7. saved unsolved MPH only.
 *
 * The solve/export step is a separate job in Kobayashi1993Solve.java.
 *
 * Parameter table (name / value / unit / source):
 *   L / 9 / m / square domain, Eq. (3)
 *   epsbar / 0.01 / m / mean interface width, Eq. (3)
 *   tau / 0.0003 / s / phase relaxation time, Eq. (3)
 *   alpha / 0.9 / 1 / liquidus slope, Eq. (4)
 *   gamma / 10 / 1 / interface kinetic coefficient, Eq. (4)
 *   Teq / 1 / 1 / equilibrium temperature, Eq. (4)
 *   Klatent / 2 / 1 / latent heat, Eq. (5)
 *   delta / 0.02 / 1 / Fig. 7 anisotropy amplitude
 *   jmode / 4 / 1 / fourfold anisotropy, Fig. 7
 *   theta0 / 0 / rad / anisotropy axis
 *   noiseAmp / 0.01 / 1 / paper noise strength
 *   noiseSeed / 1993 / 1 / declared reproduction assumption
 *   hnoise / 0.03 / m / noise correlation cell, declared assumption
 *   dtnoise / 0.0002 / s / noise update cadence, declared assumption
 *   R0 / 0.15 / m / seed radius, declared assumption
 *   D / 1 / m^2/s / dimensionless thermal diffusivity
 *   hmesh / 0.03 / m / mapped mesh size
 *   maxStep / 0.0002 / s / maximum BDF step
 *   dtout / 0.01 / s / saved output interval
 *   tfinal / 1.4 / s / equivalence of nondimensional final time
 *
 * Equation-to-feature mapping:
 *   Eq. (3) -> physics "gp", General Form PDE in field p
 *   Eq. (4) -> variables v_interface and v_source
 *   Eq. (5) -> physics "gT", General Form PDE in field T
 *   zero-flux boundaries -> default General Form PDE boundary rows
 *   initial seed -> feature "init1" in physics "gp"
 */
public final class __BUILD_CLASS__ {
  private static Model m;

  private static void parameter(String name, String expression, String description) {
    m.param().set(name, expression, description);
  }

  private static void variable(String group, String name, String expression,
                               String description) {
    m.component("comp1").variable(group).set(name, expression, description);
  }

  private static void parameters() {
/*__PARAMETER_CALLS__*/
  }

  private static void variables() {
    m.component("comp1").variable().create("v_geometry");
    m.component("comp1").variable().create("v_interface");
    m.component("comp1").variable().create("v_source");
    m.component("comp1").variable().create("v_flux");
    m.component("comp1").variable().create("v_initial");
    m.component("comp1").variable().create("v_diagnostics");

/*__VARIABLE_CALLS__*/
  }

  private static void geometry() {
    m.component("comp1").geom().create("geom1", 2);
    m.component("comp1").geom("geom1").lengthUnit("m");
    m.component("comp1").geom("geom1").create("square", "Rectangle");
    m.component("comp1").geom("geom1").feature("square")
        .set("size", new String[]{"L", "L"});
    m.component("comp1").geom("geom1").run("square");

    // Named domain selection is used by the explicit initial-value features.
    m.component("comp1").selection().create("domain", "Explicit");
    m.component("comp1").selection("domain").geom("geom1", 2);
    m.component("comp1").selection("domain").all();
  }

  private static void physics() {
    // The paper gives Eq. (3) and Eq. (5) in conservative divergence form.
    // General Form PDE is the native COMSOL feature for that form; the
    // constitutive coefficients remain named variables rather than being
    // pasted into a single expression.
    m.component("comp1").physics().create("gp", "GeneralFormPDE", "geom1", new String[]{"p"});
    m.component("comp1").physics("gp").label("Paper Eq. (3): anisotropic phase field");
    m.component("comp1").physics("gp").prop("Units").set("DependentVariableQuantity", "none");
    m.component("comp1").physics("gp").prop("Units").set("CustomDependentVariableUnit", "1");
    m.component("comp1").physics("gp").prop("Units").set("SourceTermQuantity", "none");
    m.component("comp1").physics("gp").prop("Units").set("CustomSourceTermUnit", "1/s");
    m.component("comp1").physics("gp").feature("gfeq1").setIndex(
        "Ga", new String[]{"GammaPx", "GammaPy"}, 0);
    m.component("comp1").physics("gp").feature("gfeq1").setIndex("ea", "0", 0);
    m.component("comp1").physics("gp").feature("gfeq1").setIndex("da", "tau", 0);
    m.component("comp1").physics("gp").feature("gfeq1").setIndex("f", "phaseSource", 0);
    m.component("comp1").physics("gp").feature("init1").set("p", "phaseInitial");

    // Eq. (5): T_t = D lap(T) + Klatent p_t.
    m.component("comp1").physics().create("gT", "GeneralFormPDE", "geom1", new String[]{"T"});
    m.component("comp1").physics("gT").label("Paper Eq. (5): heat and latent heat");
    m.component("comp1").physics("gT").prop("Units").set("DependentVariableQuantity", "none");
    m.component("comp1").physics("gT").prop("Units").set("CustomDependentVariableUnit", "1");
    m.component("comp1").physics("gT").prop("Units").set("SourceTermQuantity", "none");
    m.component("comp1").physics("gT").prop("Units").set("CustomSourceTermUnit", "1/s");
    m.component("comp1").physics("gT").feature("gfeq1").setIndex(
        "Ga", new String[]{"heatFluxX", "heatFluxY"}, 0);
    m.component("comp1").physics("gT").feature("gfeq1").setIndex("ea", "0", 0);
    m.component("comp1").physics("gT").feature("gfeq1").setIndex("da", "1", 0);
    m.component("comp1").physics("gT").feature("gfeq1").setIndex("f", "latentSource", 0);
    m.component("comp1").physics("gT").feature("init1").set("T", "temperatureInitial");

    // The General Form PDE default boundary is g=0, q=0 on all exterior
    // boundaries: zero general flux for p and zero heat flux for T.
  }

  private static void couplingsAndDiagnostics() {
    m.component("comp1").cpl().create("intop1", "Integration");
    m.component("comp1").cpl("intop1").selection().geom("geom1", 2);
    m.component("comp1").cpl("intop1").selection().all();
    m.component("comp1").cpl().create("maxop1", "Maximum");
    m.component("comp1").cpl("maxop1").selection().geom("geom1", 2);
    m.component("comp1").cpl("maxop1").selection().all();
    m.component("comp1").cpl().create("minop1", "Minimum");
    m.component("comp1").cpl("minop1").selection().geom("geom1", 2);
    m.component("comp1").cpl("minop1").selection().all();
  }

  private static void mesh() {
    m.component("comp1").mesh().create("mesh1");
    m.component("comp1").mesh("mesh1").create("size1", "Size");
    m.component("comp1").mesh("mesh1").feature("size1").set("custom", "on");
    m.component("comp1").mesh("mesh1").feature("size1").set("hmax", "hmesh");
    m.component("comp1").mesh("mesh1").feature("size1").set("hmin", "hmesh");
    m.component("comp1").mesh("mesh1").create("map1", "Map");
    m.component("comp1").mesh("mesh1").feature("map1").selection().geom("geom1", 2);
    m.component("comp1").mesh("mesh1").feature("map1").selection().all();
    m.component("comp1").mesh("mesh1").run();
  }

  private static void study() {
    m.study().create("std1");
    m.study("std1").create("param", "Parametric");
    m.study("std1").feature("param").set("pname", new String[]{"delta"});
    m.study("std1").feature("param").set("plistarr", new String[]{"__DELTA_VALUES__"});
    m.study("std1").create("time", "Transient");
    m.study("std1").feature("time").set("tlist", "range(0,dtout,tfinal)");
    m.study("std1").createAutoSequences("sol");

    m.sol("sol1").feature("t1").set("tlist", "range(0,dtout,tfinal)");
    m.sol("sol1").feature("t1").set("timemethod", "bdf");
    m.sol("sol1").feature("t1").set("maxorder", 2);
    m.sol("sol1").feature("t1").set("rtol", 1e-3);
    m.sol("sol1").feature("t1").set("maxstepconstraintbdf", "const");
    m.sol("sol1").feature("t1").set("maxstepbdf", "maxStep");
  }

  private static void results() {
    m.result().table().create("tblGlobal", "Table");
    m.result().numerical().create("gev1", "EvalGlobal");
    m.result().numerical("gev1").set("expr", new String[]{
        "solidArea", "enthalpyInvariant", "tipY", "halfWidth",
        "pMin", "pMax", "TMin", "TMax",
        "delta", "noiseAmp", "R0", "hmesh", "maxStep"
    });
    m.result().numerical("gev1").set("unit", new String[]{
        "m^2", "m^2", "m", "m", "1", "1", "1", "1",
        "1", "1", "m", "m", "s"
    });
    m.result().numerical("gev1").set("table", "tblGlobal");

    m.result().export().create("data1", "Data");
    m.result().export("data1").set("expr", new String[]{"p", "T"});
    m.result().export("data1").set("unit", new String[]{"1", "1"});
    m.result().export("data1").set("descr", new String[]{"phase field", "temperature"});
    m.result().export("data1").set("separator", ",");
    m.result().export("data1").set("header", "on");
    m.result().export("data1").set("location", "regulargrid");
    m.result().export("data1").set("regulargridx2", "301");
    m.result().export("data1").set("regulargridy2", "301");
  }

  public static void main(String[] args) throws Exception {
    m = ModelUtil.create("__MODEL_NAME__");
    m.label("__MODEL_LABEL__");
    m.component().create("comp1", true);
    parameters();
    geometry();
    variables();
    couplingsAndDiagnostics();
    physics();
    mesh();
    study();
    results();

    m.modelPath(".");
    m.save("__BUILD_MPH__");
  }
}
