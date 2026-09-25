/** PaperSim sensitivity-run contract for Kobayashi 1993. */

import com.comsol.model.*;
import com.comsol.model.util.*;
import java.io.IOException;

/**
 * Run one declared Kobayashi sensitivity case from the built MPH.
 *
 * The build job substitutes __VARIANT__ with one declared sensitivity case.
 */
public final class Kobayashi1993DendriteSensitivity {
  private static final String VARIANT = "__VARIANT__";

  private static double[] caseParameters(String variant) {
    if ("control_delta020".equals(variant)) {
      return new double[]{0.02, 0.03, 0.0002, 0.15, 0.00};
    }
    if ("mesh_fine".equals(variant)) {
      return new double[]{0.02, 0.02, 0.0002, 0.15, 0.00};
    }
    if ("timestep_fine".equals(variant)) {
      return new double[]{0.02, 0.03, 0.0001, 0.15, 0.00};
    }
    if ("seed_small".equals(variant)) {
      return new double[]{0.02, 0.03, 0.0002, 0.12, 0.00};
    }
    if ("seed_large".equals(variant)) {
      return new double[]{0.02, 0.03, 0.0002, 0.18, 0.00};
    }
    throw new IllegalArgumentException("unsupported sensitivity variant: " + variant);
  }

  public static void main(String[] args) throws IOException {
    String variant = VARIANT;
    if (!variant.matches("[A-Za-z0-9_.-]+")) {
      throw new IllegalArgumentException("unsafe VARIANT");
    }
    String builtMph = "iter001_built.mph";
    double[] values = caseParameters(variant);
    double delta = values[0];
    double hmesh = values[1];
    double maxStep = values[2];
    double seedRadius = values[3];
    double noiseAmp = values[4];

    Model model = ModelUtil.load("Kobayashi1993Dendrite", builtMph);
    model.param().set("delta", Double.toString(delta));
    model.param().set("hmesh", Double.toString(hmesh) + "[m]");
    model.param().set("maxStep", Double.toString(maxStep) + "[s]");
    model.param().set("R0", Double.toString(seedRadius) + "[m]");
    model.param().set("noiseAmp", Double.toString(noiseAmp));
    model.param().set("noiseSeed", "1993");
    model.param().set("tfinal", "0.8[s]");

    model.component("comp1").mesh("mesh1").run();
    model.sol("sol1").runAll();

    model.result().numerical("gev1").set("data", "dset1");
    model.result().numerical("gev1").set("innerinput", "all");
    model.result().numerical("gev1").setResult();
    model.result().table("tblGlobal").save(variant + "_global.csv");
    model.save(variant + "_solved.mph");
  }
}
